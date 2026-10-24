from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from flask.testing import FlaskClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth as auth_lib
from app.models import Booking, RoomType, User
from tests.conftest import FIXED_NOW, JWT_SECRET, add_rate, auth_headers, stay


def payload(
    room_type: RoomType, days: int = 10, nights: int = 3, guests: int = 2
) -> dict[str, Any]:
    start, end = stay(days, nights)
    return {
        "room_type_id": room_type.id,
        "check_in": start.isoformat(),
        "check_out": end.isoformat(),
        "guests": guests,
    }


def test_create_booking_returns_the_contract_shape(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User
) -> None:
    res = client.post(
        "/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(guest)
    )
    assert res.status_code == 201
    body = res.get_json()
    start, end = stay(10, 3)
    assert body == {
        "id": body["id"],
        "status": "PENDING",
        "check_in": start.isoformat(),
        "check_out": end.isoformat(),
        "nights": 3,
        "guests": 2,
        "room": {
            "id": body["room"]["id"],
            "number": "101",
            "room_type": {"id": catalog["Standard"].id, "label": "Standard"},
        },
        "expires_at": "2026-10-24T12:15:00Z",
        "price": {
            "nights": 3,
            "nightly_avg": "700.00",
            "subtotal": "2100.00",
            "discount": "0.00",
            "tax": "90.00",
            "total": "2190.00",
            "currency": "MAD",
        },
        "payment": None,
        "created_at": "2026-10-24T12:00:00Z",
    }


def test_booking_price_is_frozen_when_rates_change_later(
    client: FlaskClient, session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    created = client.post(
        "/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(guest)
    )
    start, end = stay(10, 3)
    add_rate(session, catalog["Standard"], start, end, "5000.00")
    again = client.get(f"/api/bookings/{created.get_json()['id']}", headers=auth_headers(guest))
    assert again.get_json()["price"]["total"] == "2190.00"


def test_booking_requires_authentication(client: FlaskClient, catalog: dict[str, RoomType]) -> None:
    res = client.post("/api/bookings", json=payload(catalog["Standard"]))
    assert res.status_code == 401


def test_staff_can_book_too(client: FlaskClient, catalog: dict[str, RoomType], staff: User) -> None:
    res = client.post(
        "/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(staff)
    )
    assert res.status_code == 201


def test_validation_errors(client: FlaskClient, catalog: dict[str, RoomType], guest: User) -> None:
    good = payload(catalog["Standard"])
    h = auth_headers(guest)
    bad_bodies = [
        {**good, "check_in": "2026-10-01", "check_out": "2026-10-03"},  # past
        {**good, "check_out": good["check_in"]},  # zero nights
        {**good, "check_in": "01/12/2026"},  # bad format
        {**good, "guests": 0},
        {**good, "guests": 7},
        {**good, "guests": "2"},
        {**good, "guests": 3},  # over capacity (Standard sleeps 2)
        {**good, "room_type_id": "x"},
        {k: v for k, v in good.items() if k != "guests"},
        payload(catalog["Standard"], nights=31),
    ]
    for body in bad_bodies:
        res = client.post("/api/bookings", json=body, headers=h)
        assert res.status_code == 422, body
        assert res.get_json()["error"] == "validation_error"


def test_unknown_room_type_is_404(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User
) -> None:
    res = client.post(
        "/api/bookings",
        json={**payload(catalog["Standard"]), "room_type_id": 999},
        headers=auth_headers(guest),
    )
    assert res.status_code == 404 and res.get_json()["error"] == "not_found"


def test_no_availability_is_a_409(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    body = payload(catalog["Suite"], guests=2)
    assert client.post("/api/bookings", json=body, headers=auth_headers(guest)).status_code == 201
    res = client.post("/api/bookings", json=body, headers=auth_headers(other_guest))
    assert res.status_code == 409
    assert res.get_json()["error"] == "no_availability"


def test_idempotency_key_replay_returns_200_with_the_same_booking(
    client: FlaskClient, session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    h = auth_headers(guest, **{"Idempotency-Key": "order-123"})
    first = client.post("/api/bookings", json=payload(catalog["Standard"]), headers=h)
    second = client.post("/api/bookings", json=payload(catalog["Standard"]), headers=h)
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.get_json() == first.get_json()
    assert session.scalar(select(func.count()).select_from(Booking)) == 1


def test_no_idempotency_key_creates_distinct_bookings(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User
) -> None:
    ids = {
        client.post(
            "/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(guest)
        ).get_json()["id"]
        for _ in range(2)
    }
    assert len(ids) == 2


def test_guest_lists_only_own_bookings_and_staff_sees_all(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User, other_guest: User, staff: User
) -> None:
    for user in (guest, other_guest, guest):
        client.post("/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(user))
    mine = client.get("/api/bookings", headers=auth_headers(guest)).get_json()["items"]
    assert [b["id"] for b in mine] == [3, 1]  # newest first
    everything = client.get("/api/bookings", headers=auth_headers(staff)).get_json()["items"]
    assert [b["id"] for b in everything] == [3, 2, 1]


def test_staff_status_filter(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User, staff: User
) -> None:
    created = client.post(
        "/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(guest)
    )
    client.delete(f"/api/bookings/{created.get_json()['id']}", headers=auth_headers(guest))
    client.post("/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(guest))
    h = auth_headers(staff)
    assert len(client.get("/api/bookings?status=CANCELLED", headers=h).get_json()["items"]) == 1
    assert len(client.get("/api/bookings?status=pending", headers=h).get_json()["items"]) == 1
    assert client.get("/api/bookings?status=bogus", headers=h).status_code == 422


def test_guests_never_see_other_guests_bookings(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User, other_guest: User, staff: User
) -> None:
    booking_id = client.post(
        "/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(guest)
    ).get_json()["id"]
    url = f"/api/bookings/{booking_id}"
    for method in (client.get, client.delete):
        res = method(url, headers=auth_headers(other_guest))
        assert res.status_code == 404 and res.get_json()["error"] == "not_found"
    missing = client.get("/api/bookings/9999", headers=auth_headers(other_guest))
    assert missing.get_json() == client.get(url, headers=auth_headers(other_guest)).get_json()
    assert client.get(url, headers=auth_headers(guest)).status_code == 200
    assert client.get(url, headers=auth_headers(staff)).status_code == 200


def test_cancel_returns_the_booking_and_frees_the_room(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    body = payload(catalog["Suite"], guests=2)
    booking_id = client.post("/api/bookings", json=body, headers=auth_headers(guest)).get_json()[
        "id"
    ]
    res = client.delete(f"/api/bookings/{booking_id}", headers=auth_headers(guest))
    assert res.status_code == 200 and res.get_json()["status"] == "CANCELLED"
    assert (
        client.post("/api/bookings", json=body, headers=auth_headers(other_guest)).status_code
        == 201
    )


def test_cancelling_twice_is_invalid_state(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User
) -> None:
    booking_id = client.post(
        "/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(guest)
    ).get_json()["id"]
    client.delete(f"/api/bookings/{booking_id}", headers=auth_headers(guest))
    res = client.delete(f"/api/bookings/{booking_id}", headers=auth_headers(guest))
    assert res.status_code == 409 and res.get_json()["error"] == "invalid_state"


def test_cannot_cancel_after_check_in_day(
    client: FlaskClient,
    session: Session,
    catalog: dict[str, RoomType],
    guest: User,
    frozen_clock: Callable[[datetime], None],
) -> None:
    booking_id = client.post(
        "/api/bookings",
        json=payload(catalog["Standard"], days=1, nights=3),
        headers=auth_headers(guest),
    ).get_json()["id"]
    # Make it a confirmed booking so that only the "stay already started" rule can refuse.
    booking = session.get(Booking, booking_id)
    assert booking is not None
    booking.status, booking.expires_at = "CONFIRMED", None
    session.commit()

    later = FIXED_NOW + timedelta(days=2)  # check-in was yesterday
    frozen_clock(later)
    headers = {"Authorization": f"Bearer {auth_lib.create_token(guest, JWT_SECRET, now=later)}"}
    res = client.delete(f"/api/bookings/{booking_id}", headers=headers)
    assert res.status_code == 409 and res.get_json()["error"] == "invalid_state"
    session.expire_all()
    assert session.get(Booking, booking_id).status == "CONFIRMED"  # type: ignore[union-attr]


def test_expired_hold_shows_as_expired_through_the_api(
    client: FlaskClient,
    catalog: dict[str, RoomType],
    guest: User,
    frozen_clock: Callable[[datetime], None],
) -> None:
    booking_id = client.post(
        "/api/bookings", json=payload(catalog["Standard"]), headers=auth_headers(guest)
    ).get_json()["id"]
    frozen_clock(FIXED_NOW + timedelta(minutes=16))
    res = client.get(f"/api/bookings/{booking_id}", headers=auth_headers(guest))
    assert res.get_json()["status"] == "EXPIRED"
    # And an expired booking cannot be cancelled.
    assert (
        client.delete(f"/api/bookings/{booking_id}", headers=auth_headers(guest)).status_code == 409
    )
