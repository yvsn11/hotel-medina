# ADR-002: Service layer between routes and models

Status: Accepted

## Context

The interesting rules of the system are pricing (seasonal rates, length-of-stay discounts, tourist tax), booking lifecycle (hold, confirm, cancel, expire), and payment event handling. If these live inside Flask view functions they can only be tested through HTTP, they get duplicated when a second entry point appears, and they are tied to `request` objects.

There are in fact several entry points already: HTTP routes, the Stripe webhook, the mock payment confirmation, and the `expire-holds` CLI command.

## Decision

Structure the backend in three layers:

- **Routes** (`app/routes`): parse and validate input, authenticate and authorize by role, call a service, serialize the result and map domain errors to the JSON error shape.
- **Services** (`app/services`): business rules in plain Python. They take a database session and plain values, never `request`. Pricing (`app/services/pricing.py`) is made of pure functions over `Decimal` with no database access.
- **Models** (`app/models`): SQLAlchemy persistence only.

Services raise domain exceptions (for example "no availability" or "invalid state"); a single error handler turns them into the HTTP codes in `docs/api.md`. The webhook route, the mock confirmation route and the CLI all call the same service functions.

Test coverage is measured on `app/services` with a floor of 85%, because that is where the rules are.

## Consequences

- Pricing and lifecycle rules are tested directly, including with property-based tests for pricing, without a web client.
- One implementation of "confirm a booking" serves Stripe and mock payments (see ADR-004).
- More files and a little indirection for a small app. Routes can look thin and it takes a hop to find the logic.
- Discipline is needed to keep HTTP concerns out of services; mypy and code review are the guardrails.
- The coverage threshold applies to services only, so route and model code can be under-covered without failing CI. API tests cover routes separately.

## Alternatives considered

- **Logic in the routes.** Fastest to write, hardest to test and reuse.
- **Logic in model methods (active record style).** Keeps code close to the data, but mixes persistence with cross-entity rules such as booking plus payment plus webhook dedupe.
- **Full domain model with repositories.** More ceremony than a project of this size justifies; SQLAlchemy sessions already act as the unit of work.
