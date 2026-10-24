"""Availability (public) and back office (staff)."""

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app import clock
from app.auth import require_roles
from app.config import get_settings
from app.extensions import get_session
from app.models import Role
from app.schemas import AvailabilityQuery, RateIn, RoomTypeUpdate, RoomUpdate, validate
from app.serializers import (
    availability_item_json,
    rate_json,
    room_json,
    room_type_staff_json,
)
from app.services import availability, catalog

bp = Blueprint("rooms", __name__, url_prefix="/api")


@bp.get("/rooms/available")
def available() -> ResponseReturnValue:
    query = validate(AvailabilityQuery, request.args.to_dict())
    items = availability.search_availability(
        get_session(),
        query.from_,
        query.to,
        query.guests,
        now=clock.utcnow(),
        tax_per_person_night=get_settings().tourist_tax_per_person_night,
    )
    return jsonify(
        {
            "from": query.from_.isoformat(),
            "to": query.to.isoformat(),
            "guests": query.guests,
            "items": [availability_item_json(i) for i in items],
        }
    )


@bp.get("/rooms")
@require_roles(Role.STAFF)
def list_rooms() -> ResponseReturnValue:
    return jsonify({"items": [room_json(r) for r in catalog.list_rooms(get_session())]})


@bp.put("/rooms/<int:room_id>")
@require_roles(Role.STAFF)
def update_room(room_id: int) -> ResponseReturnValue:
    data = validate(RoomUpdate, request.get_json(silent=True))
    room = catalog.update_room(get_session(), room_id, data.model_dump(exclude_unset=True))
    return jsonify(room_json(room))


@bp.put("/room-types/<int:room_type_id>")
@require_roles(Role.STAFF)
def update_room_type(room_type_id: int) -> ResponseReturnValue:
    data = validate(RoomTypeUpdate, request.get_json(silent=True))
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    return jsonify(
        room_type_staff_json(catalog.update_room_type(get_session(), room_type_id, changes))
    )


@bp.get("/room-types/<int:room_type_id>/rates")
@require_roles(Role.STAFF)
def list_rates(room_type_id: int) -> ResponseReturnValue:
    rates = catalog.list_rates(get_session(), room_type_id)
    return jsonify({"items": [rate_json(r) for r in rates]})


@bp.post("/room-types/<int:room_type_id>/rates")
@require_roles(Role.STAFF)
def add_rate(room_type_id: int) -> ResponseReturnValue:
    data = validate(RateIn, request.get_json(silent=True))
    rate = catalog.add_rate(get_session(), room_type_id, data.start, data.end, data.price)
    return jsonify(rate_json(rate)), 201
