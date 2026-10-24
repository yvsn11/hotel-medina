# Architecture decision records

Short write-ups of the decisions that shape the system. Each follows Context, Decision, Consequences, Alternatives considered. The contract they refer to is [`../api.md`](../api.md).

| ADR | Title |
|---|---|
| [001](001-exclusion-constraint.md) | Database exclusion constraint instead of application-level locking |
| [002](002-service-layer.md) | Service layer between routes and models |
| [003](003-booking-holds.md) | PENDING holds with lazy expiry and a CLI job |
| [004](004-payment-webhooks.md) | Webhook as the only path to CONFIRMED |
