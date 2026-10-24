import json
from typing import Any

import stripe
from flask import Blueprint, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from app import clock
from app.auth import current_user, require_roles
from app.config import get_settings
from app.errors import InvalidState, MalformedRequest, NotFound
from app.extensions import get_session
from app.models import Role
from app.models.booking import Booking
from app.schemas import MockConfirmIn, validate
from app.serializers import booking_json
from app.services import bookings, payments
from app.services.pricing import CURRENCY, money

bp = Blueprint("payments", __name__, url_prefix="/api")


def _provider() -> payments.PaymentProvider:
    provider: payments.PaymentProvider = current_app.extensions["payment_provider"]
    return provider


def _owned_booking(booking_id: int) -> Booking:
    """Payment endpoints are owner-only: even staff only pay their own bookings."""
    user = current_user()
    booking = bookings.get_booking_for_user(get_session(), user, booking_id)
    if booking.user_id != user.id:
        raise NotFound("Booking not found")
    return booking


@bp.post("/bookings/<int:booking_id>/pay")
@require_roles(Role.GUEST, Role.STAFF)
def pay(booking_id: int) -> ResponseReturnValue:
    booking = _owned_booking(booking_id)
    start = payments.start_payment(get_session(), _provider(), booking, now=clock.utcnow())
    body: dict[str, Any] = {
        "provider": start.provider,
        "amount": money(booking.total),
        "currency": CURRENCY,
    }
    if start.client_secret is not None:
        body["client_secret"] = start.client_secret
    return jsonify(body)


@bp.post("/payments/mock/confirm")
@require_roles(Role.GUEST, Role.STAFF)
def mock_confirm() -> ResponseReturnValue:
    if _provider().name != "mock":
        raise NotFound("Not found")
    data = validate(MockConfirmIn, request.get_json(silent=True))
    booking = _owned_booking(data.booking_id)
    if booking.payment is None:
        raise InvalidState("Start the payment first")
    payments.handle_event(get_session(), payments.mock_success_event(booking.payment))
    get_session().refresh(booking)
    return jsonify(booking_json(booking))


@bp.post("/payments/webhook")
def webhook() -> ResponseReturnValue:
    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise NotFound("Webhook is not configured")
    payload = request.get_data()
    signature = request.headers.get("Stripe-Signature", "")
    try:
        stripe.Webhook.construct_event(payload, signature, secret)
        event = json.loads(payload)
    except (
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
        stripe.SignatureVerificationError,
    ) as exc:  # a well-signed but oddly shaped body can make stripe's parser raise
        raise MalformedRequest("Invalid webhook signature or payload") from exc
    if not isinstance(event, dict) or "id" not in event:
        raise MalformedRequest("Invalid webhook payload")
    result = payments.handle_event(get_session(), event)
    return jsonify({"received": True, "result": result.value})
