"""The constraints are real: they come from the Alembic migration, on PostgreSQL."""

from datetime import date
from decimal import Decimal

import pytest
from psycopg.types.range import Range
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Booking, RoomType, User
from tests.conftest import FIXED_NOW

D = date


def _room_id(session: Session, number: str = "101") -> int:
    return int(
        session.execute(text("SELECT id FROM rooms WHERE number = :n"), {"n": number}).scalar_one()
    )


def _add_booking(
    session: Session,
    user: User,
    room_id: int,
    start: date,
    end: date,
    status: str = "PENDING",
    key: str | None = None,
) -> Booking:
    booking = Booking(
        user_id=user.id,
        room_id=room_id,
        stay=Range(start, end, "[)"),
        guests=1,
        status=status,
        total=Decimal("100"),
        idempotency_key=key,
        created_at=FIXED_NOW,
    )
    session.add(booking)
    session.flush()
    return booking


def test_btree_gist_and_constraints_exist(session: Session) -> None:
    ext = session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")).scalar()
    assert ext == 1
    defs = dict(
        session.execute(
            text("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE contype = 'x'")
        ).all()
    )
    assert "EXCLUDE USING gist (room_id WITH =, stay WITH &&)" in defs["no_overlapping_stays"]
    assert "PENDING" in defs["no_overlapping_stays"] and "CONFIRMED" in defs["no_overlapping_stays"]
    assert (
        "EXCLUDE USING gist (room_type_id WITH =, season WITH &&)" in defs["no_overlapping_rates"]
    )
    index = session.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_booking_idempotency'")
    ).scalar_one()
    assert "UNIQUE" in index and "(user_id, idempotency_key)" in index
    assert "idempotency_key IS NOT NULL" in index


def test_overlapping_active_stays_are_rejected_by_the_database(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    room = _room_id(session)
    _add_booking(session, guest, room, D(2026, 12, 1), D(2026, 12, 4))
    session.commit()
    with pytest.raises(IntegrityError, match="no_overlapping_stays"):
        _add_booking(session, other_guest, room, D(2026, 12, 3), D(2026, 12, 6), "CONFIRMED")
    session.rollback()


def test_check_out_day_is_free_for_the_next_guest(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    room = _room_id(session)
    _add_booking(session, guest, room, D(2026, 12, 1), D(2026, 12, 3))
    _add_booking(session, other_guest, room, D(2026, 12, 3), D(2026, 12, 5))
    session.commit()


@pytest.mark.parametrize("status", ["CANCELLED", "EXPIRED"])
def test_inactive_bookings_do_not_block_the_room(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User, status: str
) -> None:
    room = _room_id(session)
    _add_booking(session, guest, room, D(2026, 12, 1), D(2026, 12, 4), status)
    _add_booking(session, other_guest, room, D(2026, 12, 1), D(2026, 12, 4))
    session.commit()


def test_same_dates_in_different_rooms_are_fine(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    _add_booking(session, guest, _room_id(session, "101"), D(2026, 12, 1), D(2026, 12, 4))
    _add_booking(session, other_guest, _room_id(session, "102"), D(2026, 12, 1), D(2026, 12, 4))
    session.commit()


def test_idempotency_key_is_unique_per_user_only(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    _add_booking(session, guest, _room_id(session, "101"), D(2026, 12, 1), D(2026, 12, 2), key="k")
    _add_booking(
        session, other_guest, _room_id(session, "102"), D(2026, 12, 1), D(2026, 12, 2), key="k"
    )
    _add_booking(session, guest, _room_id(session, "103"), D(2026, 12, 1), D(2026, 12, 2))
    _add_booking(session, guest, _room_id(session, "104"), D(2026, 12, 1), D(2026, 12, 2))
    session.commit()
    with pytest.raises(IntegrityError, match="uq_booking_idempotency"):
        _add_booking(
            session, guest, _room_id(session, "201"), D(2026, 12, 1), D(2026, 12, 2), key="k"
        )
    session.rollback()


def test_overlapping_rates_are_rejected_for_the_same_room_type(
    session: Session, catalog: dict[str, RoomType]
) -> None:
    standard, deluxe = catalog["Standard"].id, catalog["Deluxe"].id
    insert = text(
        "INSERT INTO rates (room_type_id, season, price) VALUES (:t, daterange(:a, :b), 1)"
    )
    session.execute(insert, {"t": standard, "a": D(2026, 3, 1), "b": D(2026, 6, 1)})
    session.execute(insert, {"t": standard, "a": D(2026, 6, 1), "b": D(2026, 7, 1)})  # adjacent ok
    session.execute(insert, {"t": deluxe, "a": D(2026, 3, 1), "b": D(2026, 6, 1)})  # other type ok
    session.commit()
    with pytest.raises(IntegrityError, match="no_overlapping_rates"):
        session.execute(insert, {"t": standard, "a": D(2026, 5, 31), "b": D(2026, 6, 2)})
    session.rollback()
