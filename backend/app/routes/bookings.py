from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app import clock
from app.auth import current_user, require_roles
from app.config import get_settings
from app.errors import ValidationFailed
from app.extensions import get_session
from app.models import BookingStatus, Role
from app.schemas import BookingIn, validate
from app.serializers import booking_json
from app.services import bookings, holds

bp = Blueprint("bookings", __name__, url_prefix="/api/bookings")


@bp.post("")
@require_roles(Role.GUEST, Role.STAFF)
def create() -> ResponseReturnValue:
    data = validate(BookingIn, request.get_json(silent=True))
    settings = get_settings()
    result = bookings.create_booking(
        get_session(),
        bookings.BookingRequest(
            user_id=current_user().id,
            room_type_id=data.room_type_id,
            check_in=data.check_in,
            check_out=data.check_out,
            guests=data.guests,
            idempotency_key=request.headers.get("Idempotency-Key"),
        ),
        now=clock.utcnow(),
        hold_minutes=settings.hold_minutes,
        tax_per_person_night=settings.tourist_tax_per_person_night,
    )
    return jsonify(booking_json(result.booking)), 201 if result.created else 200


@bp.get("")
@require_roles(Role.GUEST, Role.STAFF)
def list_() -> ResponseReturnValue:
    status = request.args.get("status")
    if status is not None:
        status = status.upper()
        if status not in {s.value for s in BookingStatus}:
            raise ValidationFailed("Unknown status", {"fields": {"status": "unknown value"}})
    items = bookings.list_bookings(get_session(), current_user(), now=clock.utcnow(), status=status)
    return jsonify({"items": [booking_json(b) for b in items]})


@bp.get("/<int:booking_id>")
@require_roles(Role.GUEST, Role.STAFF)
def get(booking_id: int) -> ResponseReturnValue:
    holds.expire_holds(get_session(), clock.utcnow())
    booking = bookings.get_booking_for_user(get_session(), current_user(), booking_id)
    return jsonify(booking_json(booking))


@bp.delete("/<int:booking_id>")
@require_roles(Role.GUEST, Role.STAFF)
def cancel(booking_id: int) -> ResponseReturnValue:
    booking = bookings.cancel_booking(get_session(), current_user(), booking_id, now=clock.utcnow())
    return jsonify(booking_json(booking))
