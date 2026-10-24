from datetime import timedelta

import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from app.models import RoomType, User
from tests.conftest import FIXED_NOW, add_rate, auth_headers, stay


def search(client: FlaskClient, days: int = 10, nights: int = 3, guests: int | None = 2):  # type: ignore[no-untyped-def]
    start, end = stay(days, nights)
    query = f"from={start}&to={end}" + (f"&guests={guests}" if guests is not None else "")
    return client.get(f"/api/rooms/available?{query}")


def test_availability_is_public_and_lists_types_with_prices(
    client: FlaskClient, catalog: dict[str, RoomType]
) -> None:
    res = search(client)
    assert res.status_code == 200
    body = res.get_json()
    start, end = stay(10, 3)
    assert (body["from"], body["to"], body["guests"]) == (start.isoformat(), end.isoformat(), 2)
    assert [i["room_type"]["label"] for i in body["items"]] == ["Standard", "Deluxe", "Suite"]
    standard = body["items"][0]
    assert standard["available_rooms"] == 4
    assert standard["room_type"] == {
        "id": catalog["Standard"].id,
        "label": "Standard",
        "description": "Standard room",
        "capacity": 2,
    }
    assert standard["price"] == {
        "nights": 3,
        "nightly_avg": "700.00",
        "subtotal": "2100.00",
        "discount": "0.00",
        "tax": "90.00",
        "total": "2190.00",
        "currency": "MAD",
    }


def test_guests_default_to_one(client: FlaskClient, catalog: dict[str, RoomType]) -> None:
    body = search(client, guests=None).get_json()
    assert body["guests"] == 1
    assert body["items"][0]["price"]["tax"] == "45.00"


def test_capacity_filter(client: FlaskClient, catalog: dict[str, RoomType]) -> None:
    labels = [i["room_type"]["label"] for i in search(client, guests=4).get_json()["items"]]
    assert labels == ["Suite"]


def test_booked_rooms_reduce_the_count_and_full_types_disappear(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User, other_guest: User
) -> None:
    start, end = stay(10, 3)
    body = {
        "room_type_id": catalog["Suite"].id,
        "check_in": str(start),
        "check_out": str(end),
        "guests": 2,
    }
    client.post("/api/bookings", json=body, headers=auth_headers(guest))
    body["room_type_id"] = catalog["Standard"].id
    client.post("/api/bookings", json=body, headers=auth_headers(other_guest))
    items = {
        i["room_type"]["label"]: i["available_rooms"] for i in search(client).get_json()["items"]
    }
    assert items == {"Standard": 3, "Deluxe": 3}


def test_check_out_day_is_available(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User
) -> None:
    start, end = stay(10, 3)
    client.post(
        "/api/bookings",
        json={
            "room_type_id": catalog["Suite"].id,
            "check_in": str(start),
            "check_out": str(end),
            "guests": 2,
        },
        headers=auth_headers(guest),
    )
    after = client.get(f"/api/rooms/available?from={end}&to={end + timedelta(days=1)}&guests=2")
    assert "Suite" in [i["room_type"]["label"] for i in after.get_json()["items"]]


def test_maintenance_rooms_are_excluded(
    client: FlaskClient, session: Session, catalog: dict[str, RoomType], staff: User
) -> None:
    from app.models import Room

    suite_room = session.query(Room).filter_by(number="301").one()
    res = client.put(
        f"/api/rooms/{suite_room.id}", json={"status": "MAINTENANCE"}, headers=auth_headers(staff)
    )
    assert res.status_code == 200
    labels = [i["room_type"]["label"] for i in search(client, guests=1).get_json()["items"]]
    assert "Suite" not in labels


def test_seasonal_rates_and_discounts_flow_into_the_search(
    client: FlaskClient, session: Session, catalog: dict[str, RoomType]
) -> None:
    start, end = stay(10, 7)
    add_rate(session, catalog["Standard"], start, end, "875.00")
    standard = search(client, nights=7, guests=1).get_json()["items"][0]["price"]
    assert standard["subtotal"] == "6125.00" and standard["discount"] == "612.50"
    assert standard["total"] == "5617.50"


@pytest.mark.parametrize(
    "query",
    [
        "",
        "from=2026-12-01",
        "from=2026-12-01&to=2026-12-01",
        "from=2026-12-05&to=2026-12-01",
        "from=2026-10-23&to=2026-10-25",  # yesterday
        "from=2026-12-01&to=2027-01-15",  # > 30 nights
        "from=2026-12-01&to=2026-12-03&guests=0",
        "from=2026-12-01&to=2026-12-03&guests=7",
        "from=2026-12-01&to=2026-12-03&guests=abc",
        "from=yesterday&to=tomorrow",
    ],
)
def test_validation(client: FlaskClient, query: str) -> None:
    res = client.get(f"/api/rooms/available?{query}")
    assert res.status_code == 422
    assert res.get_json()["error"] == "validation_error"


def test_today_is_allowed_and_30_nights_is_the_limit(
    client: FlaskClient, catalog: dict[str, RoomType]
) -> None:
    assert search(client, days=0, nights=30).status_code == 200
    assert search(client, days=0, nights=31).status_code == 422
    assert FIXED_NOW.date().isoformat() in client.get(
        f"/api/rooms/available?from={FIXED_NOW.date()}&to={FIXED_NOW.date() + timedelta(days=1)}"
    ).get_data(as_text=True)
