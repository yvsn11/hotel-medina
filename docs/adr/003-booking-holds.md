# ADR-003: PENDING holds with lazy expiry and a CLI job

Status: Accepted

## Context

Payment takes time. If a booking is only created after payment succeeds, two guests can pay for the same room and one has to be refunded. If the booking is created before payment and never released, abandoned checkouts block rooms forever. The system needs a time-limited reservation, and a way to release it that does not require extra infrastructure on free hosting tiers.

## Decision

A booking is created as `PENDING` with `expires_at = now + HOLD_MINUTES` (default 15). A `PENDING` booking occupies the room through the exclusion constraint (ADR-001). A successful payment makes it `CONFIRMED` and clears `expires_at`. An unpaid hold becomes `EXPIRED`, which removes it from the constraint and frees the room.

Expiry is applied in two ways:

1. **Lazy.** The service calls `expire_holds()` (an update of `PENDING` bookings whose `expires_at` has passed) before availability search and before creating a booking. Anything that could be affected by a stale hold sees a clean state, so correctness does not depend on a job running.
2. **Cron-friendly CLI.** `flask --app wsgi expire-holds` runs the same function. An operator can schedule it to keep the data tidy and statuses accurate for staff views.

Payment start (`POST /api/bookings/{id}/pay`) is refused for an expired hold.

## Consequences

- No scheduler, worker process or queue to deploy, monitor or pay for. The app is a single web process plus the database.
- Correctness of availability never depends on timing of a background job, because expiry runs on the read and write paths that matter.
- Statuses can be stale between requests: an unpaid booking may still read `PENDING` after `expires_at` until something triggers expiry. Booking reads that must be exact have to check `expires_at` or call the expiry first.
- Each availability search and booking creation pays for one extra `UPDATE`. At this scale that is negligible, but it is write traffic on a read endpoint.
- A late payment on an expired hold is handled by the webhook rules in ADR-004 (ignored and logged); it needs a manual refund path, which is out of scope.
- If load or requirements grow (emails on expiry, many instances), a real scheduler can call the same function without changing behaviour.

## Alternatives considered

- **Celery or RQ worker with periodic tasks.** Standard, but adds Redis, another process and deployment cost for a task that a single SQL statement performs.
- **In-process scheduler (APScheduler) inside the web app.** Runs once per instance and dies with the process; duplicate runs with several workers.
- **PostgreSQL `pg_cron`.** Nice, but not available on every host.
- **No hold; create the booking only on payment success.** Allows paying for a room that was just taken.
- **Redis keys with TTL as the lock.** Introduces a second source of truth next to the constraint.
