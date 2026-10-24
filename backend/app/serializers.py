"""Database objects to the JSON shapes of the API contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import Booking, Payment, Rate, Room, RoomType, User
from app.services.availability import AvailabilityItem
from app.services.pricing import money


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def user_json(user: User) -> dict[str, Any]:
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


def payment_json(payment: Payment | None) -> dict[str, Any] | None:
    if payment is None:
        return None
    return {"status": payment.status, "provider": payment.provider, "amount": money(payment.amount)}


def booking_json(booking: Booking) -> dict[str, Any]:
    room = booking.room
    return {
        "id": booking.id,
        "status": booking.status,
        "check_in": booking.check_in.isoformat(),
        "check_out": booking.check_out.isoformat(),
        "nights": booking.nights,
        "guests": booking.guests,
        "room": {
            "id": room.id,
            "number": room.number,
            "room_type": {"id": room.room_type.id, "label": room.room_type.label},
        },
        "expires_at": iso(booking.expires_at),
        "price": booking.price,
        "payment": payment_json(booking.payment),
        "created_at": iso(booking.created_at),
    }


def room_type_public_json(rt: RoomType) -> dict[str, Any]:
    return {
        "id": rt.id,
        "label": rt.label,
        "description": rt.description,
        "capacity": rt.capacity,
    }


def room_type_staff_json(rt: RoomType) -> dict[str, Any]:
    return {
        "id": rt.id,
        "label": rt.label,
        "description": rt.description,
        "base_price": money(rt.base_price),
        "capacity": rt.capacity,
    }


def room_json(room: Room) -> dict[str, Any]:
    rt = room.room_type
    return {
        "id": room.id,
        "number": room.number,
        "status": room.status,
        "room_type": {
            "id": rt.id,
            "label": rt.label,
            "base_price": money(rt.base_price),
            "capacity": rt.capacity,
        },
    }


def rate_json(rate: Rate) -> dict[str, Any]:
    assert rate.season.lower is not None and rate.season.upper is not None
    return {
        "id": rate.id,
        "start": rate.season.lower.isoformat(),
        "end": rate.season.upper.isoformat(),
        "price": money(rate.price),
    }


def availability_item_json(item: AvailabilityItem) -> dict[str, Any]:
    return {
        "room_type": room_type_public_json(item.room_type),
        "available_rooms": item.available_rooms,
        "price": item.price.to_dict(),
    }
