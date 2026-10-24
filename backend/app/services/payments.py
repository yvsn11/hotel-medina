"""Payment providers (stripe, mock) and the single webhook event handler."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.errors import InvalidState
from app.models import Booking, BookingStatus, Payment, PaymentStatus, WebhookEvent
from app.services import holds
from app.services.pricing import CURRENCY

log = logging.getLogger(__name__)

EVENT_SUCCEEDED = "payment_intent.succeeded"
EVENT_FAILED = "payment_intent.payment_failed"


@dataclass(frozen=True)
class PaymentStart:
    provider: str
    provider_ref: str
    client_secret: str | None


class PaymentProvider(Protocol):
    name: str

    def create_payment(self, booking_id: int, amount: Decimal, currency: str) -> PaymentStart: ...


class MockProvider:
    name = "mock"

    def create_payment(self, booking_id: int, amount: Decimal, currency: str) -> PaymentStart:
        return PaymentStart(self.name, f"pi_mock_{booking_id}_{uuid.uuid4().hex[:12]}", None)


# (amount in minor units, currency lower-case, booking id) -> (intent id, client secret)
IntentFactory = Callable[[int, str, int], tuple[str, str]]


def _stripe_create_intent(secret_key: str) -> IntentFactory:
    def create(amount_minor: int, currency: str, booking_id: int) -> tuple[str, str]:
        import stripe  # imported lazily: only needed for real Stripe calls

        intent = stripe.PaymentIntent.create(
            amount=amount_minor,
            currency=currency,
            metadata={"booking_id": str(booking_id)},
            automatic_payment_methods={"enabled": True},
            api_key=secret_key,
        )
        return str(intent.id), str(intent.client_secret)

    return create


class StripeProvider:
    name = "stripe"

    def __init__(self, secret_key: str, create_intent: IntentFactory | None = None) -> None:
        self._create_intent = create_intent or _stripe_create_intent(secret_key)

    def create_payment(self, booking_id: int, amount: Decimal, currency: str) -> PaymentStart:
        amount_minor = int((amount * 100).to_integral_value())
        intent_id, secret = self._create_intent(amount_minor, currency.lower(), booking_id)
        return PaymentStart(self.name, intent_id, secret)


def build_provider(name: str, stripe_secret_key: str | None) -> PaymentProvider:
    if name == "stripe":
        assert stripe_secret_key
        return StripeProvider(stripe_secret_key)
    return MockProvider()


def start_payment(
    session: Session, provider: PaymentProvider, booking: Booking, *, now: datetime
) -> PaymentStart:
    """Create (or restart after a failure) the payment for a PENDING, unexpired booking."""
    holds.expire_holds(session, now)
    session.refresh(booking, with_for_update=True)
    if booking.status != BookingStatus.PENDING.value:
        session.rollback()
        raise InvalidState(f"A {booking.status} booking cannot be paid")
    if booking.expires_at is not None and booking.expires_at <= now:
        session.rollback()
        raise InvalidState("The hold on this booking has expired")

    payment = booking.payment
    start = provider.create_payment(booking.id, booking.total, CURRENCY)
    if payment is None:
        payment = Payment(booking_id=booking.id)
        session.add(payment)
    payment.amount = booking.total
    payment.provider = start.provider
    payment.provider_ref = start.provider_ref
    payment.status = PaymentStatus.REQUIRES_PAYMENT.value
    session.commit()
    return start


class EventResult(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    IGNORED = "ignored"


def mock_success_event(payment: Payment) -> dict[str, Any]:
    """The event a Stripe webhook would deliver for this payment."""
    return {
        "id": f"evt_mock_{uuid.uuid4().hex}",
        "type": EVENT_SUCCEEDED,
        "data": {
            "object": {
                "id": payment.provider_ref,
                "object": "payment_intent",
                "metadata": {"booking_id": str(payment.booking_id)},
            }
        },
    }


def handle_event(session: Session, event: dict[str, Any]) -> EventResult:
    """Apply a (verified) provider event. Idempotent by `event["id"]`; commits."""
    event_id = str(event["id"])
    inserted = session.execute(
        pg_insert(WebhookEvent)
        .values(event_id=event_id)
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(WebhookEvent.event_id)
    ).first()
    if inserted is None:
        session.rollback()
        log.info("duplicate webhook event %s acknowledged", event_id)
        return EventResult.DUPLICATE

    event_type = event.get("type")
    if event_type not in (EVENT_SUCCEEDED, EVENT_FAILED):
        session.commit()
        return EventResult.IGNORED

    obj = event.get("data", {}).get("object", {})
    payment = _find_payment(session, obj)
    if payment is None:
        log.warning("webhook event %s matches no payment", event_id)
        session.commit()
        return EventResult.IGNORED

    booking = session.get(Booking, payment.booking_id, with_for_update=True, populate_existing=True)
    assert booking is not None
    if event_type == EVENT_SUCCEEDED:
        result = _apply_success(booking, payment)
    else:
        result = _apply_failure(booking, payment)
    session.commit()
    return result


def _find_payment(session: Session, obj: dict[str, Any]) -> Payment | None:
    ref = obj.get("id")
    if ref:
        found = session.scalars(select(Payment).where(Payment.provider_ref == ref)).first()
        if found is not None:
            return found
    return None


def _apply_success(booking: Booking, payment: Payment) -> EventResult:
    if booking.status in (BookingStatus.EXPIRED.value, BookingStatus.CANCELLED.value):
        log.warning(
            "payment succeeded for %s booking %s: ignored (needs a manual refund)",
            booking.status,
            booking.id,
        )
        return EventResult.IGNORED
    payment.status = PaymentStatus.SUCCEEDED.value
    booking.status = BookingStatus.CONFIRMED.value
    booking.expires_at = None
    return EventResult.PROCESSED


def _apply_failure(booking: Booking, payment: Payment) -> EventResult:
    if payment.status == PaymentStatus.SUCCEEDED.value:
        return EventResult.IGNORED
    payment.status = PaymentStatus.FAILED.value
    return EventResult.PROCESSED
