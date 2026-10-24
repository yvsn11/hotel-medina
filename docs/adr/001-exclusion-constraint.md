# ADR-001: Database exclusion constraint instead of application-level locking

Status: Accepted

## Context

The core invariant of the system is that two active bookings never overlap on the same room. The usual implementation checks availability in application code and then inserts, which has a race: two requests can both see the room as free and both insert. The system must hold this invariant with several API processes running, and with retries and webhooks writing to the same tables.

A stay is stored as a `daterange` with `[)` bounds, so `check_out` is exclusive and a guest can arrive on the day another leaves. Only `PENDING` and `CONFIRMED` bookings occupy a room.

## Decision

Enforce the invariant in PostgreSQL with an exclusion constraint, created by the Alembic migration after `CREATE EXTENSION IF NOT EXISTS btree_gist`:

```sql
ALTER TABLE bookings ADD CONSTRAINT no_overlapping_stays
  EXCLUDE USING gist (room_id WITH =, stay WITH &&)
  WHERE (status IN ('PENDING', 'CONFIRMED'));
```

The booking service does not try to be the arbiter. It picks a candidate room that looks free and inserts; if the insert fails with an exclusion violation, it tries the next candidate room of that type, and returns `409 no_availability` when none is left. The availability search is advisory; the constraint is final. The same technique is used for seasonal rates (`no_overlapping_rates`), so two seasons cannot overlap for one room type.

The concurrency test (many simultaneous requests for one room, exactly one succeeds) exercises the constraint, not application code.

## Consequences

- Correctness does not depend on the number of API instances, on transaction isolation level tuning, or on every code path remembering to lock.
- Cancelled and expired bookings drop out of the constraint through the partial `WHERE` clause, so their rooms are free again without deleting rows.
- The database must support `btree_gist` (stock PostgreSQL contrib; checked for Neon). This ties the project to PostgreSQL and makes SQLite unusable for tests, so tests run against a real Postgres.
- Constraint violations are an expected control-flow path. The service must catch the specific error and roll back the savepoint or transaction cleanly.
- Error messages from the database are not user-facing; the API maps them to `no_availability`.

## Alternatives considered

- **Check then insert in the application.** Simple, and wrong under concurrency.
- **`SELECT ... FOR UPDATE` on the room row.** Works if every writer follows it, and serializes all bookings of a room. It relies on discipline in code, and a missed path silently breaks the invariant. It also locks even when the dates do not overlap.
- **`SERIALIZABLE` isolation with retries.** Correct, but moves complexity into retry logic and still depends on every transaction using it.
- **Advisory locks keyed by room.** Same discipline problem as row locks, and the lock lives outside the data it protects.
- **One row per room per night with a unique key.** Also database-enforced, and portable to other databases, but turns a stay into many rows and makes range queries and pricing joins clumsier.
