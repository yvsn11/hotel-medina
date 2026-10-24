"""Availability search and shared stay validation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from psycopg.types.range import Range
from sqlalchemy import ColumnElement, Select, exists, func, select
from sqlalchemy.orm import Session

from app.errors import ValidationFailed
from app.models import Booking, Rate, Room, RoomStatus, RoomType
from app.models.booking import ACTIVE_STATUSES
from app.services import holds
from app.services.pricing import Price, Season, compute_price, count_nights

MAX_NIGHTS = 30
MIN_GUESTS = 1
MAX_GUESTS = 6


@dataclass(frozen=True)
class AvailabilityItem:
    room_type: RoomType
    available_rooms: int
    price: Price


def validate_stay(check_in: date, check_out: date, today: date, guests: int) -> None:
    if check_in < today:
        raise ValidationFailed(
            "check-in must be today or later", {"fields": {"from": "in the past"}}
        )
    if check_out <= check_in:
        raise ValidationFailed(
            "check-out must be after check-in", {"fields": {"to": "not after from"}}
        )
    if count_nights(check_in, check_out) > MAX_NIGHTS:
        raise ValidationFailed(f"a stay is at most {MAX_NIGHTS} nights")
    if not MIN_GUESTS <= guests <= MAX_GUESTS:
        raise ValidationFailed(f"guests must be between {MIN_GUESTS} and {MAX_GUESTS}")


def stay_range(check_in: date, check_out: date) -> Range[date]:
    return Range(check_in, check_out, "[)")


def is_free(check_in: date, check_out: date) -> ColumnElement[bool]:
    """SQL condition: the room has no active booking overlapping the stay."""
    overlapping = exists().where(
        Booking.room_id == Room.id,
        Booking.status.in_(ACTIVE_STATUSES),
        Booking.stay.overlaps(stay_range(check_in, check_out)),
    )
    return ~overlapping


def free_rooms_query(room_type_id: int, check_in: date, check_out: date) -> Select[tuple[Room]]:
    return (
        select(Room)
        .where(
            Room.room_type_id == room_type_id,
            Room.status == RoomStatus.AVAILABLE.value,
            is_free(check_in, check_out),
        )
        .order_by(Room.number)
    )


def load_seasons(
    session: Session, room_type_ids: list[int], check_in: date, check_out: date
) -> dict[int, list[Season]]:
    rows = session.scalars(
        select(Rate).where(
            Rate.room_type_id.in_(room_type_ids),
            Rate.season.overlaps(stay_range(check_in, check_out)),
        )
    )
    seasons: dict[int, list[Season]] = defaultdict(list)
    for rate in rows:
        assert rate.season.lower is not None and rate.season.upper is not None
        seasons[rate.room_type_id].append(Season(rate.season.lower, rate.season.upper, rate.price))
    return seasons


def price_for(
    room_type: RoomType,
    seasons: list[Season],
    check_in: date,
    check_out: date,
    guests: int,
    tax_per_person_night: Decimal,
) -> Price:
    return compute_price(
        check_in, check_out, room_type.base_price, seasons, guests, tax_per_person_night
    )


def search_availability(
    session: Session,
    check_in: date,
    check_out: date,
    guests: int,
    *,
    now: datetime,
    tax_per_person_night: Decimal,
) -> list[AvailabilityItem]:
    validate_stay(check_in, check_out, now.date(), guests)
    holds.expire_holds(session, now)

    rows = session.execute(
        select(RoomType, func.count(Room.id))
        .join(Room, Room.room_type_id == RoomType.id)
        .where(
            RoomType.capacity >= guests,
            Room.status == RoomStatus.AVAILABLE.value,
            is_free(check_in, check_out),
        )
        .group_by(RoomType.id)
        .order_by(RoomType.base_price, RoomType.id)
    ).all()
    seasons = load_seasons(session, [rt.id for rt, _ in rows], check_in, check_out)
    return [
        AvailabilityItem(
            room_type=rt,
            available_rooms=count,
            price=price_for(
                rt, seasons.get(rt.id, []), check_in, check_out, guests, tax_per_person_night
            ),
        )
        for rt, count in rows
    ]
