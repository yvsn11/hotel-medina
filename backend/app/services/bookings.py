"""Booking creation, lookup and cancellation (no Flask)."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum, auto

import psycopg.errors
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.errors import InvalidState, NoAvailability, NotFound, ValidationFailed
from app.models import Booking, BookingStatus, Role, RoomType, User
from app.models.booking import ACTIVE_STATUSES
from app.services import holds
from app.services.availability import (
    free_rooms_query,
    load_seasons,
    price_for,
    stay_range,
    validate_stay,
)
from app.services.pricing import CURRENCY

log = logging.getLogger(__name__)

IDEMPOTENCY_CONSTRAINT = "uq_booking_idempotency"
MAX_DEADLOCK_RETRIES = 6
MAX_KEY_LENGTH = 255


@dataclass(frozen=True)
class BookingRequest:
    user_id: int
    room_type_id: int
    check_in: date
    check_out: date
    guests: int
    idempotency_key: str | None = None


@dataclass(frozen=True)
class BookingResult:
    booking: Booking
    created: bool


class _Outcome(Enum):
    INSERTED = auto()
    ROOM_TAKEN = auto()
    DUPLICATE_KEY = auto()


def _find_by_key(session: Session, user_id: int, key: str | None) -> Booking | None:
    if key is None:
        return None
    return session.scalars(
        select(Booking).where(Booking.user_id == user_id, Booking.idempotency_key == key)
    ).first()


def _try_insert(session: Session, booking: Booking) -> _Outcome:
    """Insert inside a savepoint. The database constraints are the final arbiter."""
    for attempt in range(MAX_DEADLOCK_RETRIES):
        try:
            with session.begin_nested():
                session.add(booking)
                session.flush()
            return _Outcome.INSERTED
        except IntegrityError as exc:
            orig = exc.orig
            if isinstance(orig, psycopg.errors.ExclusionViolation):
                return _Outcome.ROOM_TAKEN
            if (
                isinstance(orig, psycopg.errors.UniqueViolation)
                and orig.diag.constraint_name == IDEMPOTENCY_CONSTRAINT
            ):
                return _Outcome.DUPLICATE_KEY
            raise
        except OperationalError as exc:
            # Two inserts racing for the same room can deadlock on the exclusion
            # constraint; the loser is aborted by Postgres and simply retries.
            if not isinstance(
                exc.orig, psycopg.errors.DeadlockDetected | psycopg.errors.SerializationFailure
            ):
                raise
            log.info("retrying booking insert after %s", type(exc.orig).__name__)
            time.sleep(random.uniform(0.005, 0.03) * (attempt + 1))  # noqa: S311
            booking = _clone(booking)
    raise NoAvailability("The room could not be reserved, please retry")


def _clone(b: Booking) -> Booking:
    return Booking(
        user_id=b.user_id,
        room_id=b.room_id,
        stay=b.stay,
        guests=b.guests,
        status=b.status,
        expires_at=b.expires_at,
        idempotency_key=b.idempotency_key,
        total=b.total,
        currency=b.currency,
        price=b.price,
        created_at=b.created_at,
    )


def create_booking(
    session: Session,
    req: BookingRequest,
    *,
    now: datetime,
    hold_minutes: int,
    tax_per_person_night: Decimal,
) -> BookingResult:
    key = req.idempotency_key
    if key is not None and not 0 < len(key) <= MAX_KEY_LENGTH:
        raise ValidationFailed("Idempotency-Key must be 1 to 255 characters")

    replay = _find_by_key(session, req.user_id, key)
    if replay is not None:
        return BookingResult(replay, created=False)

    validate_stay(req.check_in, req.check_out, now.date(), req.guests)
    room_type = session.get(RoomType, req.room_type_id)
    if room_type is None:
        raise NotFound("Room type not found")
    if req.guests > room_type.capacity:
        raise ValidationFailed(f"This room type sleeps at most {room_type.capacity} guests")

    holds.expire_holds(session, now)

    seasons = load_seasons(session, [room_type.id], req.check_in, req.check_out)
    price = price_for(
        room_type,
        seasons.get(room_type.id, []),
        req.check_in,
        req.check_out,
        req.guests,
        tax_per_person_night,
    )
    stay = stay_range(req.check_in, req.check_out)

    candidates = session.scalars(free_rooms_query(room_type.id, req.check_in, req.check_out)).all()
    for room in candidates:
        booking = Booking(
            user_id=req.user_id,
            room_id=room.id,
            stay=stay,
            guests=req.guests,
            status=BookingStatus.PENDING.value,
            expires_at=now + timedelta(minutes=hold_minutes),
            idempotency_key=key,
            total=price.total,
            currency=CURRENCY,
            price=price.to_dict(),
            created_at=now,
        )
        outcome = _try_insert(session, booking)
        if outcome is _Outcome.INSERTED:
            session.commit()
            return BookingResult(booking, created=True)
        if outcome is _Outcome.DUPLICATE_KEY:
            return _replay_after_race(session, req)
        # ROOM_TAKEN: another request won this room; try the next candidate.

    # Nothing free. A concurrent request with the same key may have won every room.
    existing = _find_by_key(session, req.user_id, key)
    if existing is not None:
        return BookingResult(existing, created=False)
    raise NoAvailability("No room of this type is available for these dates")


def _replay_after_race(session: Session, req: BookingRequest) -> BookingResult:
    session.rollback()
    existing = _find_by_key(session, req.user_id, req.idempotency_key)
    if existing is None:  # pragma: no cover - the unique index guarantees it exists
        raise NoAvailability("No room of this type is available for these dates")
    return BookingResult(existing, created=False)


def get_booking_for_user(
    session: Session, user: User, booking_id: int, *, lock: bool = False
) -> Booking:
    """Staff see everything; guests only their own bookings (others are 404)."""
    booking = session.get(Booking, booking_id, with_for_update=lock, populate_existing=lock)
    if booking is None or (user.role != Role.STAFF.value and booking.user_id != user.id):
        raise NotFound("Booking not found")
    return booking


def list_bookings(
    session: Session, user: User, *, now: datetime, status: str | None = None
) -> list[Booking]:
    holds.expire_holds(session, now)
    query = select(Booking).order_by(Booking.created_at.desc(), Booking.id.desc())
    if user.role != Role.STAFF.value:
        query = query.where(Booking.user_id == user.id)
    if status is not None:
        query = query.where(Booking.status == status)
    return list(session.scalars(query))


def cancel_booking(session: Session, user: User, booking_id: int, *, now: datetime) -> Booking:
    holds.expire_holds(session, now)
    booking = get_booking_for_user(session, user, booking_id, lock=True)
    if booking.status not in ACTIVE_STATUSES:
        session.rollback()
        raise InvalidState(f"A {booking.status} booking cannot be cancelled")
    if booking.check_in < now.date():
        session.rollback()
        raise InvalidState("A stay that already started cannot be cancelled")
    booking.status = BookingStatus.CANCELLED.value
    session.commit()
    return booking
