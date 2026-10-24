"""Payments: mock provider, injected fake Stripe, and signed webhooks (no network)."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import Booking, Payment, RoomType, User, WebhookEvent
from app.services import payments
from app.services.payments import EventResult, StripeProvider
from tests.conftest import FIXED_NOW, WEBHOOK_SECRET, auth_headers, make_app, stay


def new_booking(client: FlaskClient, room_type: RoomType, user: User, **kw: Any) -> dict[str, Any]:
    start, end = stay(10, 3)
    res = client.post(
        "/api/bookings",
        json={
            "room_type_id": room_type.id,
            "check_in": str(start),
            "check_out": str(end),
            "guests": 2,
        },
        headers=auth_headers(user, **kw),
    )
    assert res.status_code == 201
    return res.get_json()  # type: ignore[no-any-return]


def reload(session: Session, model: type[Booking] | type[Payment], pk: int) -> Any:
    session.expire_all()
    return session.get(model, pk)


# ---- mock provider -----------------------------------------------------------------------


def test_mock_pay_then_confirm_confirms_the_booking(
    client: FlaskClient, session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    booking = new_booking(client, catalog["Standard"], guest)
    pay = client.post(f"/api/bookings/{booking['id']}/pay", headers=auth_headers(guest))
    assert pay.status_code == 200
    assert pay.get_json() == {"provider": "mock", "amount": "2190.00", "currency": "MAD"}

    mid = client.get(f"/api/bookings/{booking['id']}", headers=auth_headers(guest)).get_json()
    assert mid["status"] == "PENDING"
    assert mid["payment"] == {"status": "REQUIRES_PAYMENT", "provider": "mock", "amount": "2190.00"}

    done = client.post(
        "/api/payments/mock/confirm",
        json={"booking_id": booking["id"]},
        headers=auth_headers(guest),
    )
    assert done.status_code == 200
    body = done.get_json()
    assert body["status"] == "CONFIRMED" and body["expires_at"] is None
    assert body["payment"]["status"] == "SUCCEEDED"
    assert session.scalar(select(func.count()).select_from(WebhookEvent)) == 1


def test_mock_confirm_twice_is_harmless(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User
) -> None:
    booking = new_booking(client, catalog["Standard"], guest)
    client.post(f"/api/bookings/{booking['id']}/pay", headers=auth_headers(guest))
    for _ in range(2):
        res = client.post(
            "/api/payments/mock/confirm",
            json={"booking_id": booking["id"]},
            headers=auth_headers(guest),
        )
        assert res.status_code == 200 and res.get_json()["status"] == "CONFIRMED"


def test_mock_confirm_requires_payment_to_have_started(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User
) -> None:
    booking = new_booking(client, catalog["Standard"], guest)
    res = client.post(
        "/api/payments/mock/confirm",
        json={"booking_id": booking["id"]},
        headers=auth_headers(guest),
    )
    assert res.status_code == 409 and res.get_json()["error"] == "invalid_state"


def test_payment_endpoints_are_owner_only(
    client: FlaskClient, catalog: dict[str, RoomType], guest: User, other_guest: User, staff: User
) -> None:
    booking = new_booking(client, catalog["Standard"], guest)
    pay_url = f"/api/bookings/{booking['id']}/pay"
    assert client.post(pay_url).status_code == 401
    for stranger in (other_guest, staff):
        assert client.post(pay_url, headers=auth_headers(stranger)).status_code == 404
        res = client.post(
            "/api/payments/mock/confirm",
            json={"booking_id": booking["id"]},
            headers=auth_headers(stranger),
        )
        assert res.status_code == 404
    assert client.post("/api/bookings/9999/pay", headers=auth_headers(guest)).status_code == 404


def test_cannot_pay_expired_cancelled_or_already_paid_bookings(
    client: FlaskClient,
    catalog: dict[str, RoomType],
    guest: User,
    frozen_clock: Callable[[datetime], None],
) -> None:
    h = auth_headers(guest)
    cancelled = new_booking(client, catalog["Standard"], guest)
    client.delete(f"/api/bookings/{cancelled['id']}", headers=h)
    paid = new_booking(client, catalog["Standard"], guest)
    client.post(f"/api/bookings/{paid['id']}/pay", headers=h)
    client.post("/api/payments/mock/confirm", json={"booking_id": paid["id"]}, headers=h)
    stale = new_booking(client, catalog["Deluxe"], guest)

    for booking_id in (cancelled["id"], paid["id"]):
        res = client.post(f"/api/bookings/{booking_id}/pay", headers=h)
        assert res.status_code == 409 and res.get_json()["error"] == "invalid_state"

    later = FIXED_NOW + timedelta(minutes=20)
    frozen_clock(later)
    h2 = auth_headers(guest)
    h2["Authorization"] = f"Bearer {_token(guest, later)}"
    res = client.post(f"/api/bookings/{stale['id']}/pay", headers=h2)
    assert res.status_code == 409 and res.get_json()["error"] == "invalid_state"


def _token(user: User, now: datetime) -> str:
    from app import auth as auth_lib
    from tests.conftest import JWT_SECRET

    return auth_lib.create_token(user, JWT_SECRET, now=now)


def test_mock_confirm_validates_its_body(client: FlaskClient, guest: User) -> None:
    res = client.post("/api/payments/mock/confirm", json={}, headers=auth_headers(guest))
    assert res.status_code == 422


# ---- stripe provider with an injected fake -------------------------------------------------


class FakeIntents:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, int]] = []

    def __call__(self, amount_minor: int, currency: str, booking_id: int) -> tuple[str, str]:
        self.calls.append((amount_minor, currency, booking_id))
        n = len(self.calls)
        return f"pi_test_{n}", f"pi_test_{n}_secret_abc"


@pytest.fixture
def fake_intents() -> FakeIntents:
    return FakeIntents()


@pytest.fixture
def stripe_client(app: Flask, fake_intents: FakeIntents) -> Iterator[FlaskClient]:
    stripe_app = make_app(PAYMENT_PROVIDER="stripe", STRIPE_SECRET_KEY="sk_test_fake")
    stripe_app.extensions["payment_provider"] = StripeProvider("sk_test_fake", fake_intents)
    yield stripe_app.test_client()
    with stripe_app.app_context():
        db.engine.dispose()


def test_stripe_pay_creates_a_payment_intent_and_returns_the_client_secret(
    stripe_client: FlaskClient,
    session: Session,
    fake_intents: FakeIntents,
    catalog: dict[str, RoomType],
    guest: User,
) -> None:
    booking = new_booking(stripe_client, catalog["Standard"], guest)
    res = stripe_client.post(f"/api/bookings/{booking['id']}/pay", headers=auth_headers(guest))
    assert res.status_code == 200
    assert res.get_json() == {
        "provider": "stripe",
        "client_secret": "pi_test_1_secret_abc",
        "amount": "2190.00",
        "currency": "MAD",
    }
    assert fake_intents.calls == [(219000, "mad", booking["id"])]
    payment = session.scalars(select(Payment)).one()
    assert (payment.provider, payment.provider_ref, payment.status) == (
        "stripe",
        "pi_test_1",
        "REQUIRES_PAYMENT",
    )


def test_stripe_mode_has_no_mock_confirm_endpoint(
    stripe_client: FlaskClient, catalog: dict[str, RoomType], guest: User
) -> None:
    booking = new_booking(stripe_client, catalog["Standard"], guest)
    stripe_client.post(f"/api/bookings/{booking['id']}/pay", headers=auth_headers(guest))
    res = stripe_client.post(
        "/api/payments/mock/confirm",
        json={"booking_id": booking["id"]},
        headers=auth_headers(guest),
    )
    assert res.status_code == 404 and res.get_json()["error"] == "not_found"


def test_paying_again_after_a_failure_creates_a_fresh_intent(
    stripe_client: FlaskClient,
    session: Session,
    fake_intents: FakeIntents,
    catalog: dict[str, RoomType],
    guest: User,
) -> None:
    booking = new_booking(stripe_client, catalog["Standard"], guest)
    pay_url = f"/api/bookings/{booking['id']}/pay"
    stripe_client.post(pay_url, headers=auth_headers(guest))
    deliver(
        stripe_client, event("evt_f1", "payment_intent.payment_failed", "pi_test_1", booking["id"])
    )
    assert session.scalars(select(Payment)).one().status == "FAILED"

    second = stripe_client.post(pay_url, headers=auth_headers(guest))
    assert second.get_json()["client_secret"] == "pi_test_2_secret_abc"
    session.expire_all()
    payment = session.scalars(select(Payment)).one()
    assert (payment.status, payment.provider_ref) == ("REQUIRES_PAYMENT", "pi_test_2")
    assert len(fake_intents.calls) == 2


# ---- webhook -----------------------------------------------------------------------------


def event(event_id: str, type_: str, intent_id: str, booking_id: int) -> dict[str, Any]:
    return {
        "id": event_id,
        "object": "event",
        "type": type_,
        "data": {
            "object": {
                "id": intent_id,
                "object": "payment_intent",
                "metadata": {"booking_id": str(booking_id)},
            }
        },
    }


def sign(payload: bytes, secret: str = WEBHOOK_SECRET, timestamp: int | None = None) -> str:
    """A Stripe-Signature header: HMAC-SHA256 over `{timestamp}.{payload}`."""
    ts = int(time.time()) if timestamp is None else timestamp
    signed = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def deliver(client: FlaskClient, body: dict[str, Any], **kw: Any) -> Any:
    payload = json.dumps(body).encode()
    return client.post(
        "/api/payments/webhook",
        data=payload,
        headers={"Stripe-Signature": sign(payload, **kw), "Content-Type": "application/json"},
    )


@pytest.fixture
def started(
    stripe_client: FlaskClient, catalog: dict[str, RoomType], guest: User
) -> dict[str, Any]:
    """A PENDING booking with a started Stripe payment (intent pi_test_1)."""
    booking = new_booking(stripe_client, catalog["Standard"], guest)
    stripe_client.post(f"/api/bookings/{booking['id']}/pay", headers=auth_headers(guest))
    return booking


def test_signed_success_event_confirms_the_booking(
    stripe_client: FlaskClient, session: Session, started: dict[str, Any]
) -> None:
    res = deliver(
        stripe_client, event("evt_1", "payment_intent.succeeded", "pi_test_1", started["id"])
    )
    assert res.status_code == 200
    booking = reload(session, Booking, started["id"])
    assert booking.status == "CONFIRMED" and booking.expires_at is None
    assert booking.payment.status == "SUCCEEDED"


def test_bad_signature_is_a_400_and_changes_nothing(
    stripe_client: FlaskClient, session: Session, started: dict[str, Any]
) -> None:
    payload = json.dumps(
        event("evt_1", "payment_intent.succeeded", "pi_test_1", started["id"])
    ).encode()
    good = sign(payload)
    tampered_digest = good[:-4] + ("0000" if not good.endswith("0000") else "1111")
    headers_to_try = [
        {},
        {"Stripe-Signature": ""},
        {"Stripe-Signature": "garbage"},
        {"Stripe-Signature": tampered_digest},
        {"Stripe-Signature": sign(payload, secret="whsec_wrong")},
        {"Stripe-Signature": sign(payload, timestamp=int(time.time()) - 3600)},  # replayed too late
    ]
    for headers in headers_to_try:
        res = stripe_client.post("/api/payments/webhook", data=payload, headers=headers)
        assert res.status_code == 400, headers
        assert res.get_json()["error"] == "validation_error"
    # A signature for different bytes does not validate this body either.
    res = stripe_client.post(
        "/api/payments/webhook", data=payload + b" ", headers={"Stripe-Signature": good}
    )
    assert res.status_code == 400
    assert reload(session, Booking, started["id"]).status == "PENDING"
    assert session.scalar(select(func.count()).select_from(WebhookEvent)) == 0


def test_validly_signed_garbage_is_a_400(stripe_client: FlaskClient) -> None:
    for payload in (b"not json", b"[1, 2]", b'{"no_id": true}'):
        res = stripe_client.post(
            "/api/payments/webhook", data=payload, headers={"Stripe-Signature": sign(payload)}
        )
        assert res.status_code == 400


def test_duplicate_events_are_acknowledged_without_effect(
    stripe_client: FlaskClient, session: Session, started: dict[str, Any]
) -> None:
    body = event("evt_dup", "payment_intent.succeeded", "pi_test_1", started["id"])
    first = deliver(stripe_client, body)
    assert first.get_json()["result"] == "processed"
    booking = reload(session, Booking, started["id"])
    booking.status = "CANCELLED"  # if the duplicate were re-applied it would not matter here...
    session.commit()
    second = deliver(stripe_client, body)
    assert second.status_code == 200 and second.get_json()["result"] == "duplicate"
    assert reload(session, Booking, started["id"]).status == "CANCELLED"  # ...it was not touched
    assert session.scalar(select(func.count()).select_from(WebhookEvent)) == 1


@pytest.mark.parametrize("status", ["EXPIRED", "CANCELLED"])
def test_success_for_expired_or_cancelled_bookings_is_ignored(
    stripe_client: FlaskClient, session: Session, started: dict[str, Any], status: str
) -> None:
    booking = reload(session, Booking, started["id"])
    booking.status = status
    session.commit()
    res = deliver(
        stripe_client, event("evt_late", "payment_intent.succeeded", "pi_test_1", started["id"])
    )
    assert res.status_code == 200 and res.get_json()["result"] == "ignored"
    booking = reload(session, Booking, started["id"])
    assert booking.status == status
    assert booking.payment.status == "REQUIRES_PAYMENT"


def test_hold_expiry_then_late_success_does_not_resurrect_the_booking(
    stripe_client: FlaskClient,
    session: Session,
    started: dict[str, Any],
    frozen_clock: Callable[[datetime], None],
) -> None:
    from app.services import holds

    frozen_clock(FIXED_NOW + timedelta(minutes=30))
    assert holds.expire_holds(session, FIXED_NOW + timedelta(minutes=30)) == 1
    res = deliver(
        stripe_client, event("evt_x", "payment_intent.succeeded", "pi_test_1", started["id"])
    )
    assert res.get_json()["result"] == "ignored"
    assert reload(session, Booking, started["id"]).status == "EXPIRED"


def test_failure_event_marks_payment_failed_and_keeps_the_hold(
    stripe_client: FlaskClient, session: Session, started: dict[str, Any]
) -> None:
    res = deliver(
        stripe_client,
        event("evt_fail", "payment_intent.payment_failed", "pi_test_1", started["id"]),
    )
    assert res.status_code == 200
    booking = reload(session, Booking, started["id"])
    assert booking.status == "PENDING" and booking.expires_at is not None
    assert booking.payment.status == "FAILED"


def test_failure_after_success_does_not_undo_the_payment(
    stripe_client: FlaskClient, session: Session, started: dict[str, Any]
) -> None:
    deliver(stripe_client, event("evt_ok", "payment_intent.succeeded", "pi_test_1", started["id"]))
    res = deliver(
        stripe_client, event("evt_bad", "payment_intent.payment_failed", "pi_test_1", started["id"])
    )
    assert res.get_json()["result"] == "ignored"
    assert reload(session, Booking, started["id"]).payment.status == "SUCCEEDED"


def test_unknown_events_and_unknown_payments_are_acknowledged(
    stripe_client: FlaskClient, session: Session, started: dict[str, Any]
) -> None:
    other_type = deliver(
        stripe_client, event("evt_c", "charge.refunded", "pi_test_1", started["id"])
    )
    unknown_pi = deliver(stripe_client, event("evt_u", "payment_intent.succeeded", "pi_nope", 999))
    assert other_type.status_code == 200 and unknown_pi.status_code == 200
    assert reload(session, Booking, started["id"]).status == "PENDING"


def test_webhook_needs_no_jwt_but_a_configured_secret(client: FlaskClient, app: Flask) -> None:
    no_secret = make_app(STRIPE_WEBHOOK_SECRET="")
    res = no_secret.test_client().post("/api/payments/webhook", data=b"{}")
    assert res.status_code == 404
    with no_secret.app_context():
        db.engine.dispose()


def test_mock_and_webhook_paths_share_one_handler(
    client: FlaskClient, session: Session, catalog: dict[str, RoomType], guest: User
) -> None:
    """A webhook-style event for a mock payment confirms the booking exactly like mock/confirm."""
    booking = new_booking(client, catalog["Standard"], guest)
    client.post(f"/api/bookings/{booking['id']}/pay", headers=auth_headers(guest))
    ref = session.scalars(select(Payment)).one().provider_ref
    assert ref is not None
    res = deliver(client, event("evt_m", "payment_intent.succeeded", ref, booking["id"]))
    assert res.status_code == 200
    assert reload(session, Booking, booking["id"]).status == "CONFIRMED"


def test_concurrent_deliveries_of_the_same_event_are_applied_once(
    app: Flask, session: Session, catalog: dict[str, RoomType], guest: User, client: FlaskClient
) -> None:
    booking = new_booking(client, catalog["Standard"], guest)
    client.post(f"/api/bookings/{booking['id']}/pay", headers=auth_headers(guest))
    ref = session.scalars(select(Payment)).one().provider_ref
    assert ref is not None
    body = event("evt_race", "payment_intent.succeeded", ref, booking["id"])
    results: list[EventResult] = []
    barrier = threading.Barrier(10)

    def worker() -> None:
        with app.app_context():
            barrier.wait(timeout=30)
            results.append(payments.handle_event(db.session(), body))
            db.session.remove()

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert Counter(results) == Counter({EventResult.PROCESSED: 1, EventResult.DUPLICATE: 9})
    assert reload(session, Booking, booking["id"]).status == "CONFIRMED"


def test_stripe_provider_builds_the_real_call_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default intent factory calls stripe.PaymentIntent.create with the right arguments."""
    import stripe

    seen: dict[str, Any] = {}

    class Intent:
        id = "pi_real_1"
        client_secret = "pi_real_1_secret"

    def fake_create(**kwargs: Any) -> Intent:
        seen.update(kwargs)
        return Intent()

    monkeypatch.setattr(stripe.PaymentIntent, "create", fake_create)
    from decimal import Decimal

    start = StripeProvider("sk_test_abc").create_payment(7, Decimal("2940.00"), "MAD")
    assert (start.provider_ref, start.client_secret) == ("pi_real_1", "pi_real_1_secret")
    assert seen["amount"] == 294000 and seen["currency"] == "mad"
    assert seen["metadata"] == {"booking_id": "7"} and seen["api_key"] == "sk_test_abc"
