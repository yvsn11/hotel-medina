"""Real concurrent bookings: separate threads, separate sessions, one real PostgreSQL.

The database exclusion constraint must let exactly one request win each room.
"""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from flask import Flask
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NoAvailability
from app.extensions import db
from app.models import Booking, Room, RoomType, User
from app.services import bookings
from app.services.bookings import BookingRequest
from tests.conftest import FIXED_NOW, add_user, stay


def run_concurrently(
    app: Flask,
    attempts: int,
    make_request: Callable[[int], BookingRequest],
    monkeypatch: pytest.MonkeyPatch,
    *,
    align_inserts: bool = True,
) -> Counter[str]:
    """Fire `attempts` booking requests at the same instant, each in its own thread/session.

    With `align_inserts`, every thread waits (after it has read the free rooms) until all
    threads are about to insert, so all of them really do see the room as free and the
    database constraint is what decides the winner.
    """
    barrier = threading.Barrier(attempts)
    insert_barrier = threading.Barrier(attempts)
    first_insert = threading.local()
    real_try_insert = bookings._try_insert

    def aligned_try_insert(session: Session, booking: Booking) -> bookings._Outcome:
        if not getattr(first_insert, "done", False):
            first_insert.done = True
            insert_barrier.wait(timeout=30)
        return real_try_insert(session, booking)

    if align_inserts:
        monkeypatch.setattr(bookings, "_try_insert", aligned_try_insert)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        with app.app_context():
            try:
                barrier.wait(timeout=30)
                result = bookings.create_booking(
                    db.session(),
                    make_request(i),
                    now=FIXED_NOW,
                    hold_minutes=15,
                    tax_per_person_night=Decimal("15.00"),
                )
                outcome = "created" if result.created else "replayed"
            except NoAvailability:
                outcome = "no_availability"
            except Exception as exc:  # pragma: no cover - reported by the assertion below
                outcome = f"error:{type(exc).__name__}:{exc}"
            finally:
                db.session.remove()
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not any(t.is_alive() for t in threads), "a booking attempt hung"
    return Counter(outcomes)


def make_users(session: Session, n: int) -> list[int]:
    return [add_user(session, f"user{i}@example.com").id for i in range(n)]


def active_bookings(session: Session, room_type: RoomType) -> list[tuple[int, date, date]]:
    rows = session.execute(
        select(Booking.room_id, Booking.stay)
        .join(Room, Room.id == Booking.room_id)
        .where(Room.room_type_id == room_type.id, Booking.status == "PENDING")
    ).all()
    return [(room_id, rng.lower, rng.upper) for room_id, rng in rows]


def test_50_concurrent_attempts_for_a_single_room_yield_exactly_one_booking(
    app: Flask, session: Session, catalog: dict[str, RoomType], monkeypatch: pytest.MonkeyPatch
) -> None:
    suite = catalog["Suite"]  # exactly one room (301)
    user_ids = make_users(session, 50)
    start, end = stay(30, 3)

    result = run_concurrently(
        app, 50, lambda i: BookingRequest(user_ids[i], suite.id, start, end, 2), monkeypatch
    )

    assert result == Counter({"created": 1, "no_availability": 49}), result
    session.expire_all()
    assert len(active_bookings(session, suite)) == 1
    assert session.scalar(select(func.count()).select_from(Booking)) == 1


def test_20_concurrent_attempts_for_three_rooms_yield_exactly_three_bookings(
    app: Flask, session: Session, catalog: dict[str, RoomType], monkeypatch: pytest.MonkeyPatch
) -> None:
    deluxe = catalog["Deluxe"]  # exactly three rooms (201-203)
    user_ids = make_users(session, 20)
    start, end = stay(30, 2)

    result = run_concurrently(
        app, 20, lambda i: BookingRequest(user_ids[i], deluxe.id, start, end, 2), monkeypatch
    )

    assert result == Counter({"created": 3, "no_availability": 17}), result
    session.expire_all()
    booked = active_bookings(session, deluxe)
    assert len({room_id for room_id, _, _ in booked}) == 3  # three different rooms


def test_overlapping_but_not_identical_dates_still_allow_one_winner(
    app: Flask, session: Session, catalog: dict[str, RoomType], monkeypatch: pytest.MonkeyPatch
) -> None:
    suite = catalog["Suite"]
    user_ids = make_users(session, 12)
    base, _ = stay(30, 1)

    def request(i: int) -> BookingRequest:
        from datetime import timedelta

        start = base + timedelta(days=i % 3)  # all stays overlap on day base+2
        return BookingRequest(user_ids[i], suite.id, start, base + timedelta(days=3 + i % 3), 1)

    result = run_concurrently(app, 12, request, monkeypatch)
    assert result["created"] == 1 and result["no_availability"] == 11, result


def test_concurrent_replays_of_one_idempotency_key_create_a_single_booking(
    app: Flask,
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    standard = catalog["Standard"]  # 4 rooms: without idempotency, all 20 would succeed
    start, end = stay(30, 2)
    guest_id = guest.id

    result = run_concurrently(
        app,
        20,
        lambda i: BookingRequest(guest_id, standard.id, start, end, 2, "same-key"),
        monkeypatch,
    )

    assert result["created"] == 1, result
    assert result["created"] + result["replayed"] == 20, result
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Booking)) == 1


def test_concurrent_replays_when_only_one_room_exists(
    app: Flask,
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The losers lose the room race, yet must still answer with the winner's booking."""
    suite = catalog["Suite"]
    start, end = stay(30, 2)
    guest_id = guest.id

    result = run_concurrently(
        app,
        20,
        lambda i: BookingRequest(guest_id, suite.id, start, end, 2, "only-key"),
        monkeypatch,
    )

    assert result["created"] == 1 and result["replayed"] == 19, result
