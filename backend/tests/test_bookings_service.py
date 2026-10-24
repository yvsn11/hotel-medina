"""Booking, holds and idempotency rules, tested without Flask requests."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg.errors
import pytest
from sqlalchemy import Select, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.errors import InvalidState, NoAvailability, NotFound, ValidationFailed
from app.models import Booking, BookingStatus, Role, Room, RoomType, User
from app.services import availability, bookings, holds
from app.services.bookings import BookingRequest
from tests.conftest import FIXED_NOW, add_rate, stay

TAX = Decimal("15.00")


def book(
    session: Session,
    user: User,
    room_type: RoomType,
    start: date,
    end: date,
    *,
    guests: int = 2,
    key: str | None = None,
    now: datetime = FIXED_NOW,
) -> bookings.BookingResult:
    return bookings.create_booking(
        session,
        BookingRequest(user.id, room_type.id, start, end, guests, key),
        now=now,
        hold_minutes=15,
        tax_per_person_night=TAX,
    )


def count_bookings(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(Booking)) or 0)


def test_creates_pending_hold_with_price_and_first_free_room(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(10, 3)
    result = book(session, guest, catalog["Standard"], start, end)
    b = result.booking
    assert result.created
    assert b.status == "PENDING"
    assert b.room.number == "101"
    assert b.expires_at == FIXED_NOW + timedelta(minutes=15)
    assert b.total == Decimal("2190.00")  # 3 * 700 + 15 * 2 * 3
    assert b.price is not None and b.price["total"] == "2190.00"
    assert (b.check_in, b.check_out, b.nights) == (start, end, 3)


def test_seasonal_rate_is_used_for_the_booking_price(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(10, 2)
    add_rate(session, catalog["Standard"], start, end, "875.00")
    assert book(session, guest, catalog["Standard"], start, end).booking.total == Decimal("1810.00")


def test_next_candidate_room_is_used_when_the_first_is_taken(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    start, end = stay(10, 2)
    first = book(session, guest, catalog["Standard"], start, end).booking
    second = book(session, other_guest, catalog["Standard"], start, end).booking
    assert (first.room.number, second.room.number) == ("101", "102")


def _stale_candidates(monkeypatch: pytest.MonkeyPatch, numbers: list[str]) -> None:
    """Make the Python-side availability check lie: it reports `numbers` as free."""

    def stale(room_type_id: int, check_in: date, check_out: date) -> Select[tuple[Room]]:
        return select(Room).where(Room.number.in_(numbers)).order_by(Room.number)

    monkeypatch.setattr(bookings, "free_rooms_query", stale)


def test_database_constraint_overrules_a_stale_availability_check(
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    other_guest: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidates [201] look free to Python but 201 is booked: the DB must refuse."""
    start, end = stay(10, 2)
    assert book(session, guest, catalog["Deluxe"], start, end).booking.room.number == "201"
    _stale_candidates(monkeypatch, ["201"])
    with pytest.raises(NoAvailability):
        book(session, other_guest, catalog["Deluxe"], start, end)
    assert count_bookings(session) == 1


def test_next_candidate_is_tried_after_a_constraint_violation(
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    other_guest: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start, end = stay(10, 2)
    assert book(session, guest, catalog["Deluxe"], start, end).booking.room.number == "201"
    _stale_candidates(monkeypatch, ["201", "202"])  # 201 is taken, 202 really is free
    assert book(session, other_guest, catalog["Deluxe"], start, end).booking.room.number == "202"


def test_no_availability_when_every_room_is_taken(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    start, end = stay(10, 2)
    book(session, guest, catalog["Suite"], start, end, guests=2)
    with pytest.raises(NoAvailability):
        book(session, other_guest, catalog["Suite"], start, end, guests=2)
    assert count_bookings(session) == 1


def test_maintenance_rooms_are_not_booked(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    from app.models import RoomStatus

    session.execute(
        Room.__table__.update()
        .where(Room.room_type_id == catalog["Suite"].id)
        .values(status=RoomStatus.MAINTENANCE.value)
    )
    session.commit()
    start, end = stay(10, 2)
    with pytest.raises(NoAvailability):
        book(session, guest, catalog["Suite"], start, end)


def test_back_to_back_stays_share_a_room(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    start, mid = stay(10, 2)
    end = mid + timedelta(days=2)
    a = book(session, guest, catalog["Suite"], start, mid).booking
    b = book(session, other_guest, catalog["Suite"], mid, end).booking
    assert a.room_id == b.room_id


def test_idempotent_replay_returns_the_original_and_creates_nothing(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(10, 2)
    first = book(session, guest, catalog["Standard"], start, end, key="abc")
    again = book(session, guest, catalog["Standard"], start, end, key="abc")
    assert first.created and not again.created
    assert again.booking.id == first.booking.id
    assert count_bookings(session) == 1


def test_idempotency_keys_are_scoped_to_the_user(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    start, end = stay(10, 2)
    a = book(session, guest, catalog["Standard"], start, end, key="same")
    b = book(session, other_guest, catalog["Standard"], start, end, key="same")
    assert a.booking.id != b.booking.id and b.created


def test_replay_is_returned_even_when_the_rooms_are_now_gone(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    start, end = stay(10, 2)
    first = book(session, guest, catalog["Suite"], start, end, key="k1")
    again = book(session, guest, catalog["Suite"], start, end, key="k1")
    assert again.booking.id == first.booking.id
    with pytest.raises(NoAvailability):
        book(session, other_guest, catalog["Suite"], start, end, key="k2")


def test_duplicate_key_race_is_resolved_to_a_replay(
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both requests passed the pre-check; the unique index decides and the loser replays."""
    start, end = stay(10, 2)
    winner = book(session, guest, catalog["Standard"], start, end, key="race").booking
    winner_id = winner.id
    real_find = bookings._find_by_key
    calls = {"n": 0}

    def blind_first_lookup(s: Session, user_id: int, key: str | None) -> Booking | None:
        calls["n"] += 1
        return None if calls["n"] == 1 else real_find(s, user_id, key)

    monkeypatch.setattr(bookings, "_find_by_key", blind_first_lookup)
    result = book(session, guest, catalog["Standard"], start, end, key="race")
    assert not result.created and result.booking.id == winner_id
    assert count_bookings(session) == 1


def test_idempotency_key_length_is_validated(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(10, 2)
    with pytest.raises(ValidationFailed):
        book(session, guest, catalog["Standard"], start, end, key="x" * 256)
    with pytest.raises(ValidationFailed):
        book(session, guest, catalog["Standard"], start, end, key="")


@pytest.mark.parametrize(
    ("offset", "nights", "guests"),
    [(-1, 2, 1), (5, 0, 1), (5, 31, 1), (5, 2, 0), (5, 2, 7)],
)
def test_invalid_stays_are_rejected(
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    offset: int,
    nights: int,
    guests: int,
) -> None:
    start, end = stay(offset, 1)
    end = start + timedelta(days=nights)
    with pytest.raises(ValidationFailed):
        book(session, guest, catalog["Standard"], start, end, guests=guests)


def test_guests_over_room_capacity_and_unknown_type(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(5, 2)
    with pytest.raises(ValidationFailed):
        book(session, guest, catalog["Standard"], start, end, guests=3)
    with pytest.raises(NotFound):
        bookings.create_booking(
            session,
            BookingRequest(guest.id, 9999, start, end, 1),
            now=FIXED_NOW,
            hold_minutes=15,
            tax_per_person_night=TAX,
        )


# ---- holds -------------------------------------------------------------------------------


def test_expire_holds_frees_the_room(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    start, end = stay(10, 2)
    held = book(session, guest, catalog["Suite"], start, end).booking
    held_id = held.id
    with pytest.raises(NoAvailability):
        book(session, other_guest, catalog["Suite"], start, end)

    later = FIXED_NOW + timedelta(minutes=15, seconds=1)
    assert holds.expire_holds(session, later) == 1
    assert session.get(Booking, held_id, populate_existing=True).status == "EXPIRED"  # type: ignore[union-attr]
    assert book(session, other_guest, catalog["Suite"], start, end, now=later).created


def test_hold_is_still_active_just_before_expiry(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(10, 2)
    b = book(session, guest, catalog["Suite"], start, end).booking
    assert holds.expire_holds(session, FIXED_NOW + timedelta(minutes=14, seconds=59)) == 0
    assert b.status == "PENDING"


def test_booking_creation_lazily_expires_old_holds(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    start, end = stay(10, 2)
    old = book(session, guest, catalog["Suite"], start, end).booking
    old_id = old.id
    # Backdate the hold instead of moving the clock.
    old.expires_at = FIXED_NOW - timedelta(minutes=1)
    session.commit()
    fresh = book(session, other_guest, catalog["Suite"], start, end)
    assert fresh.created
    assert session.get(Booking, old_id, populate_existing=True).status == "EXPIRED"  # type: ignore[union-attr]


def test_availability_search_lazily_expires_old_holds(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(10, 2)
    b = book(session, guest, catalog["Suite"], start, end).booking
    b.expires_at = FIXED_NOW - timedelta(seconds=1)
    session.commit()
    items = availability.search_availability(
        session, start, end, 4, now=FIXED_NOW, tax_per_person_night=TAX
    )
    assert [i.room_type.label for i in items] == ["Suite"]


def test_confirmed_and_cancelled_bookings_are_never_expired(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(10, 2)
    a = book(session, guest, catalog["Standard"], start, end).booking
    c = book(session, guest, catalog["Standard"], start, end).booking
    a.status, a.expires_at = BookingStatus.CONFIRMED.value, None
    c.status = BookingStatus.CANCELLED.value
    c.expires_at = FIXED_NOW - timedelta(hours=1)
    session.commit()
    assert holds.expire_holds(session, FIXED_NOW + timedelta(days=1)) == 0
    assert (a.status, c.status) == ("CONFIRMED", "CANCELLED")


# ---- availability, access and cancellation ------------------------------------------------


def test_availability_counts_and_filters_by_capacity(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(10, 3)
    book(session, guest, catalog["Standard"], start, end)
    items = availability.search_availability(
        session, start, end, 2, now=FIXED_NOW, tax_per_person_night=TAX
    )
    assert {i.room_type.label: i.available_rooms for i in items} == {
        "Standard": 3,
        "Deluxe": 3,
        "Suite": 1,
    }
    three = availability.search_availability(
        session, start, end, 3, now=FIXED_NOW, tax_per_person_night=TAX
    )
    assert [i.room_type.label for i in three] == ["Deluxe", "Suite"]


def test_guest_cannot_read_or_cancel_someone_elses_booking(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User, staff: User
) -> None:
    start, end = stay(10, 2)
    b = book(session, guest, catalog["Standard"], start, end).booking
    with pytest.raises(NotFound):
        bookings.get_booking_for_user(session, other_guest, b.id)
    with pytest.raises(NotFound):
        bookings.cancel_booking(session, other_guest, b.id, now=FIXED_NOW)
    assert bookings.get_booking_for_user(session, staff, b.id).id == b.id
    assert staff.role == Role.STAFF.value


def test_cancel_frees_the_room_and_rejects_a_second_cancel(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    start, end = stay(10, 2)
    b = book(session, guest, catalog["Suite"], start, end).booking
    cancelled = bookings.cancel_booking(session, guest, b.id, now=FIXED_NOW)
    assert cancelled.status == "CANCELLED"
    assert book(session, other_guest, catalog["Suite"], start, end).created
    with pytest.raises(InvalidState):
        bookings.cancel_booking(session, guest, b.id, now=FIXED_NOW)


def test_cannot_cancel_once_the_stay_started(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(1, 3)
    b = book(session, guest, catalog["Suite"], start, end).booking
    b_id = b.id
    # Two days later the stay is underway (check_in is in the past).
    with pytest.raises(InvalidState):
        bookings.cancel_booking(session, guest, b_id, now=FIXED_NOW + timedelta(days=2))


def test_can_cancel_on_the_day_of_check_in(
    session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(0, 2)
    b = book(session, guest, catalog["Suite"], start, end).booking
    assert bookings.cancel_booking(session, guest, b.id, now=FIXED_NOW).status == "CANCELLED"


def test_list_bookings_filters_and_orders_newest_first(
    session: Session, catalog: dict[str, RoomType], guest: User, other_guest: User, staff: User
) -> None:
    start, end = stay(10, 2)
    a = book(session, guest, catalog["Standard"], start, end, now=FIXED_NOW).booking
    b = book(
        session, guest, catalog["Standard"], start, end, now=FIXED_NOW + timedelta(minutes=1)
    ).booking
    c = book(
        session, other_guest, catalog["Standard"], start, end, now=FIXED_NOW + timedelta(minutes=2)
    ).booking
    now = FIXED_NOW + timedelta(minutes=3)
    assert [x.id for x in bookings.list_bookings(session, guest, now=now)] == [b.id, a.id]
    assert [x.id for x in bookings.list_bookings(session, staff, now=now)] == [c.id, b.id, a.id]
    assert bookings.list_bookings(session, staff, now=now, status="CONFIRMED") == []


# ---- deadlock retry, defensive branches ---------------------------------------------------


def _deadlock() -> OperationalError:
    return OperationalError("INSERT", {}, psycopg.errors.DeadlockDetected("deadlock detected"))


def test_a_deadlock_victim_retries_and_still_gets_the_room(
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_flush = session.flush
    failures = {"left": 2}

    def flaky_flush(*args: Any, **kwargs: Any) -> None:
        if failures["left"] > 0 and any(isinstance(o, Booking) for o in session.new):
            failures["left"] -= 1
            raise _deadlock()
        real_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", flaky_flush)
    monkeypatch.setattr(bookings.time, "sleep", lambda _s: None)
    start, end = stay(10, 2)
    result = book(session, guest, catalog["Standard"], start, end)
    assert result.created and failures["left"] == 0
    assert count_bookings(session) == 1


def test_persistent_deadlocks_give_up_with_a_409(
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_flush = session.flush

    def always_deadlock(*args: Any, **kwargs: Any) -> None:
        if any(isinstance(o, Booking) for o in session.new):
            raise _deadlock()
        real_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", always_deadlock)
    monkeypatch.setattr(bookings.time, "sleep", lambda _s: None)
    start, end = stay(10, 2)
    with pytest.raises(NoAvailability):
        book(session, guest, catalog["Standard"], start, end)


def test_other_database_errors_are_not_swallowed(
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise OperationalError("INSERT", {}, psycopg.errors.AdminShutdown("gone"))

    monkeypatch.setattr(session, "flush", broken)
    start, end = stay(10, 2)
    with pytest.raises(OperationalError):
        book(session, guest, catalog["Standard"], start, end)
    session.rollback()


def test_start_payment_refuses_a_hold_that_ended_but_was_not_swept_yet(
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.errors import InvalidState
    from app.services import payments

    start, end = stay(10, 2)
    booking = book(session, guest, catalog["Standard"], start, end).booking
    monkeypatch.setattr(
        payments.holds, "expire_holds", lambda s, n: 0
    )  # sweep skipped (row locked)
    with pytest.raises(InvalidState, match="expired"):
        payments.start_payment(
            session, payments.MockProvider(), booking, now=FIXED_NOW + timedelta(minutes=16)
        )
