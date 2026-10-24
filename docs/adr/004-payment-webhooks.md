# ADR-004: Webhook as the only path to CONFIRMED

Status: Accepted

## Context

The browser is not a trustworthy witness of payment: a user can close the tab after paying, or call an endpoint claiming they paid. Stripe confirms a payment by delivering a signed event to the server, and may deliver the same event more than once or out of order. The public demo also has to work without Stripe keys.

## Decision

- **A booking becomes `CONFIRMED` only through the payment event handler.** No route lets a client set that status. `POST /api/payments/webhook` verifies the `Stripe-Signature` header with `STRIPE_WEBHOOK_SECRET` (`400` on failure) and dispatches `payment_intent.succeeded` (booking `CONFIRMED`, payment `SUCCEEDED`) and `payment_intent.payment_failed` (payment `FAILED`; the booking stays `PENDING` until its hold expires).
- **Deduplication by event id.** Each `event.id` is inserted into `webhook_events` (primary key) in the same transaction as the state change. A duplicate delivery hits the key, is acknowledged with `200`, and changes nothing.
- **Late or irrelevant events are ignored safely.** A success event for an `EXPIRED` or `CANCELLED` booking is logged and acknowledged without changing the booking, so retries stop.
- **Mock provider uses the same handler.** `POST /api/payments/mock/confirm` (available only when the provider is `mock`, otherwise `404`) builds the event object Stripe would send and feeds it to the same handler, skipping only signature verification. Tests and the keyless demo therefore exercise the real confirmation code.

## Consequences

- Payment status is consistent with what the provider recorded, and a closed tab does not lose a payment.
- The system is eventually consistent: after paying, the UI must wait or poll until the webhook has been processed, and a misconfigured webhook leaves bookings `PENDING` until the hold expires.
- Insert-with-dedupe in one transaction makes retries safe, but the handler must remain idempotent in its other effects too.
- A payment that succeeds after the hold expired is acknowledged and logged but not honored; the money needs a manual refund. This is a known gap and is listed as out of scope.
- The mock path shares the handler but not signature verification, so signature code is covered by its own tests.
- Local development against real Stripe requires a tunnel or the Stripe CLI to deliver webhooks.

## Alternatives considered

- **Confirm from the client's success redirect or an endpoint the SPA calls.** Forgeable and lossy.
- **Poll Stripe from the server after checkout.** Works without public webhooks, but adds latency, rate-limit exposure and a scheduler.
- **Separate code path for mock payments.** Simpler to write and would let the demo drift from production behaviour.
- **Dedupe by checking current booking status only.** Handles the common case, but does not cover events that are not state transitions and races between two simultaneous deliveries; the event-id key is simple and atomic.
