import pytest
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from app.models import Room, RoomType, User
from tests.conftest import auth_headers

STAFF_ENDPOINTS = [
    ("get", "/api/rooms"),
    ("put", "/api/rooms/1"),
    ("put", "/api/room-types/1"),
    ("get", "/api/room-types/1/rates"),
    ("post", "/api/room-types/1/rates"),
]


@pytest.mark.parametrize(("method", "url"), STAFF_ENDPOINTS)
def test_staff_endpoints_reject_anonymous_and_guests(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User, method: str, url: str
) -> None:
    call = getattr(client, method)
    assert call(url, json={}).status_code == 401
    res = call(url, json={}, headers=auth_headers(guest))
    assert res.status_code == 403
    assert res.get_json()["error"] == "forbidden"


def test_list_rooms(client: FlaskClient, catalog: dict[str, RoomType], staff: User) -> None:
    items = client.get("/api/rooms", headers=auth_headers(staff)).get_json()["items"]
    assert [r["number"] for r in items] == ["101", "102", "103", "104", "201", "202", "203", "301"]
    assert items[0] == {
        "id": items[0]["id"],
        "number": "101",
        "status": "AVAILABLE",
        "room_type": {
            "id": catalog["Standard"].id,
            "label": "Standard",
            "base_price": "700.00",
            "capacity": 2,
        },
    }


def test_update_room(
    client: FlaskClient, session: Session, catalog: dict[str, RoomType], staff: User
) -> None:
    room = session.query(Room).filter_by(number="101").one()
    h = auth_headers(staff)
    res = client.put(
        f"/api/rooms/{room.id}", json={"status": "MAINTENANCE", "number": "1010"}, headers=h
    )
    assert res.status_code == 200
    assert (res.get_json()["status"], res.get_json()["number"]) == ("MAINTENANCE", "1010")
    assert (
        client.put(f"/api/rooms/{room.id}", json={"status": "BROKEN"}, headers=h).status_code == 422
    )
    assert client.put(f"/api/rooms/{room.id}", json={"number": ""}, headers=h).status_code == 422
    assert client.put("/api/rooms/999", json={"status": "AVAILABLE"}, headers=h).status_code == 404


def test_room_number_must_stay_unique(
    client: FlaskClient, session: Session, catalog: dict[str, RoomType], staff: User
) -> None:
    room = session.query(Room).filter_by(number="101").one()
    res = client.put(f"/api/rooms/{room.id}", json={"number": "102"}, headers=auth_headers(staff))
    assert res.status_code == 409 and res.get_json()["error"] == "invalid_state"


def test_update_room_type(client: FlaskClient, catalog: dict[str, RoomType], staff: User) -> None:
    h = auth_headers(staff)
    url = f"/api/room-types/{catalog['Standard'].id}"
    res = client.put(
        url, json={"label": "Classic", "base_price": "750.5", "capacity": 3}, headers=h
    )
    assert res.status_code == 200
    assert res.get_json() == {
        "id": catalog["Standard"].id,
        "label": "Classic",
        "description": "Standard room",
        "base_price": "750.50",
        "capacity": 3,
    }
    only_description = client.put(url, json={"description": "New text"}, headers=h).get_json()
    assert only_description["description"] == "New text" and only_description["label"] == "Classic"
    for bad in (
        {"base_price": -1},
        {"base_price": "abc"},
        {"capacity": 0},
        {"base_price": "1.234"},
    ):
        assert client.put(url, json=bad, headers=h).status_code == 422, bad
    assert client.put("/api/room-types/999", json={"label": "x"}, headers=h).status_code == 404


def test_rates_crud_and_overlap(
    client: FlaskClient, catalog: dict[str, RoomType], staff: User
) -> None:
    h = auth_headers(staff)
    url = f"/api/room-types/{catalog['Standard'].id}/rates"
    created = client.post(
        url, json={"start": "2026-12-20", "end": "2027-01-05", "price": "900"}, headers=h
    )
    assert created.status_code == 201
    assert created.get_json() == {
        "id": created.get_json()["id"],
        "start": "2026-12-20",
        "end": "2027-01-05",
        "price": "900.00",
    }
    # Adjacent (end is exclusive) is fine.
    assert (
        client.post(
            url, json={"start": "2027-01-05", "end": "2027-01-10", "price": "800"}, headers=h
        ).status_code
        == 201
    )
    overlap = client.post(
        url, json={"start": "2026-12-31", "end": "2027-01-02", "price": "1000"}, headers=h
    )
    assert overlap.status_code == 409 and overlap.get_json()["error"] == "invalid_state"
    # Another room type may use the same dates.
    other = f"/api/room-types/{catalog['Deluxe'].id}/rates"
    assert (
        client.post(
            other, json={"start": "2026-12-20", "end": "2027-01-05", "price": "1500"}, headers=h
        ).status_code
        == 201
    )

    listed = client.get(url, headers=h).get_json()["items"]
    assert [(r["start"], r["end"], r["price"]) for r in listed] == [
        ("2026-12-20", "2027-01-05", "900.00"),
        ("2027-01-05", "2027-01-10", "800.00"),
    ]


def test_rate_validation_and_unknown_type(
    client: FlaskClient, catalog: dict[str, RoomType], staff: User
) -> None:
    h = auth_headers(staff)
    url = f"/api/room-types/{catalog['Standard'].id}/rates"
    for bad in (
        {"start": "2026-12-20", "end": "2026-12-20", "price": "900"},
        {"start": "2026-12-20", "end": "2026-12-10", "price": "900"},
        {"start": "2026-12-20", "end": "2026-12-25", "price": "-5"},
        {"start": "nope", "end": "2026-12-25", "price": "5"},
        {"start": "2026-12-20", "end": "2026-12-25"},
    ):
        assert client.post(url, json=bad, headers=h).status_code == 422, bad
    assert client.get("/api/room-types/999/rates", headers=h).status_code == 404
    assert (
        client.post(
            "/api/room-types/999/rates",
            json={"start": "2026-12-20", "end": "2026-12-25", "price": "5"},
            headers=h,
        ).status_code
        == 404
    )


def test_new_rate_changes_availability_pricing(
    client: FlaskClient, catalog: dict[str, RoomType], staff: User
) -> None:
    h = auth_headers(staff)
    client.post(
        f"/api/room-types/{catalog['Standard'].id}/rates",
        json={"start": "2026-12-01", "end": "2026-12-10", "price": "1000"},
        headers=h,
    )
    res = client.get("/api/rooms/available?from=2026-12-02&to=2026-12-04&guests=1").get_json()
    assert res["items"][0]["price"]["subtotal"] == "2000.00"
