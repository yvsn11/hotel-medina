# Hotel Medina: API contract

This document is the single source of truth shared by the backend, frontend and infra work. If an implementation needs to deviate, update this file in the same change.

All endpoints live under `/api`, speak JSON, and return errors as:

```json
{ "error": "machine_code", "message": "Human readable text", "details": {} }
```

| HTTP | Meaning |
|---|---|
| 400 / 422 | Malformed or invalid input (`error`: `validation_error`) |
| 401 | Missing or invalid token (`unauthorized`) |
| 403 | Authenticated but role not allowed (`forbidden`) |
| 404 | Not found (`not_found`) |
| 409 | Conflict (`no_availability`, `invalid_state`, `email_taken`) |

Authentication: `Authorization: Bearer <jwt>`. JWTs are short-lived (60 minutes) and carry `sub` (user id) and `role`.

Roles: `guest`, `staff`.

Money: decimals serialized as strings with 2 decimals (`"1250.00"`), currency `MAD`.
Dates: ISO `YYYY-MM-DD`. Timestamps: ISO 8601 UTC.
`check_out` is exclusive (a stay from 2026-12-01 to 2026-12-03 is 2 nights, and another guest can check in on 2026-12-03).

## Stack and layout

| Piece | Choice |
|---|---|
| Backend | Python 3.11+, Flask 3, SQLAlchemy 2, Alembic (via Flask-Migrate), psycopg 3, PyJWT, OpenAPI docs served at `/api/docs` (spec at `/api/openapi.json`) |
| Database | PostgreSQL 15+, extension `btree_gist` |
| Frontend | React 18, Vite, Tailwind CSS, react-router, i18next (fr, en), Vitest + Testing Library |
| Backend entry points | app factory `app:create_app`, WSGI entry `backend/wsgi.py` (`wsgi:app`), served by gunicorn in production |
| Flask CLI (`flask --app wsgi ...`) | `db upgrade`, `seed`, `expire-holds` |
| Backend commands (run in `backend/`) | `pytest --cov=app/services --cov-fail-under=85`, `ruff check .`, `ruff format --check .`, `mypy app` |
| Frontend commands (run in `frontend/`) | `npm ci`, `npm run dev`, `npm run build`, `npm test`, `npm run lint` |

Ownership while building: backend work only touches `backend/` (except Dockerfiles), frontend work only touches `frontend/` (except Dockerfiles), infra work owns the repo root, `.github/`, `docs/` (except this file), and the two Dockerfiles.

## Environment variables

| Variable | Used by | Default / notes |
|---|---|---|
| `DATABASE_URL` | API | e.g. `postgresql+psycopg://medina:medina@db:5432/medina`. A plain `postgresql://` or `postgres://` URL (as given by Neon, Render, Supabase) must be accepted and normalized to the psycopg 3 driver. |
| `TEST_DATABASE_URL` | tests | Postgres database used by pytest, e.g. `postgresql+psycopg://postgres@127.0.0.1:5433/medina_test` |
| `JWT_SECRET` | API | required in production |
| `CORS_ORIGINS` | API | comma-separated list, e.g. `http://localhost:5173` |
| `HOLD_MINUTES` | API | `15` |
| `TOURIST_TAX_PER_PERSON_NIGHT` | API | `15.00` (MAD; illustrative, configurable) |
| `PAYMENT_PROVIDER` | API | `stripe` or `mock`. Defaults to `stripe` when `STRIPE_SECRET_KEY` is set, otherwise `mock`. |
| `STRIPE_SECRET_KEY` | API | test-mode key (`sk_test_...`) |
| `STRIPE_WEBHOOK_SECRET` | API | `whsec_...` |
| `VITE_API_URL` | frontend build | empty in dev (Vite proxies `/api` to `http://localhost:5000`); full API origin in production |
| `VITE_STRIPE_PUBLISHABLE_KEY` | frontend build | optional; when empty the UI uses the mock payment flow |

## Data model

```
users(id, email unique, password_hash, full_name, role, created_at)
room_types(id, label, description, base_price numeric(10,2), capacity)
rooms(id, number unique, status, room_type_id -> room_types)         status: AVAILABLE | MAINTENANCE
rates(id, room_type_id -> room_types, season daterange, price numeric(10,2))
bookings(id, user_id -> users, room_id -> rooms, stay daterange '[)', guests,
         status, expires_at, idempotency_key, total, currency, created_at)
         status: PENDING | CONFIRMED | CANCELLED | EXPIRED
payments(id, booking_id -> bookings unique, amount, status, provider,
         provider_ref, created_at)                                     status: REQUIRES_PAYMENT | SUCCEEDED | FAILED
webhook_events(event_id primary key, received_at)                      deduplicates provider events
```

Database-level guarantees (Alembic migration, `CREATE EXTENSION IF NOT EXISTS btree_gist`):

```sql
-- no two active bookings overlap on the same room
ALTER TABLE bookings ADD CONSTRAINT no_overlapping_stays
  EXCLUDE USING gist (room_id WITH =, stay WITH &&)
  WHERE (status IN ('PENDING', 'CONFIRMED'));

-- no two seasonal rates overlap for the same room type
ALTER TABLE rates ADD CONSTRAINT no_overlapping_rates
  EXCLUDE USING gist (room_type_id WITH =, season WITH &&);

-- idempotency: one booking per (user, key)
CREATE UNIQUE INDEX uq_booking_idempotency ON bookings (user_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
```

Holds: a booking starts `PENDING` with `expires_at = now + HOLD_MINUTES`. Expired holds are released lazily (the service runs `expire_holds()` before availability search and booking creation) and by the CLI command `flask --app wsgi expire-holds` for a cron job. A successful payment sets the booking `CONFIRMED` and clears `expires_at`.

## Pricing (pure functions, `app/services/pricing.py`)

For each night of the stay, the price is the matching `rates` season price for the room type, otherwise the room type `base_price`.

```
subtotal = sum of nightly prices
discount = subtotal * 5%  for stays of 4 to 6 nights
         = subtotal * 10% for stays of 7 nights or more
tax      = TOURIST_TAX_PER_PERSON_NIGHT * guests * nights      (not discounted)
total    = subtotal - discount + tax
```

All amounts are `Decimal`, rounded half-up to 2 decimals. Price object returned by the API:

```json
{ "nights": 3, "nightly_avg": "950.00", "subtotal": "2850.00", "discount": "0.00",
  "tax": "90.00", "total": "2940.00", "currency": "MAD" }
```

## Endpoints

### Health

`GET /api/health` (public) returns `200 {"status": "ok"}` and checks the database connection.

### Auth

`POST /api/auth/register` (public)
Body: `{ "email", "password" (min 8), "full_name" }`. Creates a `guest`. Returns `201 { "token", "user" }`. `409 email_taken`.

`POST /api/auth/login` (public)
Body: `{ "email", "password" }`. Returns `200 { "token", "user" }` or `401 unauthorized`.

`user` = `{ "id", "email", "full_name", "role" }`.

### Availability

`GET /api/rooms/available?from=YYYY-MM-DD&to=YYYY-MM-DD&guests=2` (public)

Validation: `from` is today or later, `to` is after `from`, stay is at most 30 nights, `guests` between 1 and 6 (default 1). Only room types with `capacity >= guests` and at least one free, non-maintenance room are returned.

```json
{
  "from": "2026-12-01", "to": "2026-12-04", "guests": 2,
  "items": [
    {
      "room_type": { "id": 1, "label": "Standard", "description": "...", "capacity": 2 },
      "available_rooms": 3,
      "price": { "nights": 3, "nightly_avg": "...", "subtotal": "...", "discount": "...", "tax": "...", "total": "...", "currency": "MAD" }
    }
  ]
}
```

### Bookings

Booking object:

```json
{
  "id": 12, "status": "PENDING", "check_in": "2026-12-01", "check_out": "2026-12-04",
  "nights": 3, "guests": 2,
  "room": { "id": 5, "number": "101", "room_type": { "id": 1, "label": "Standard" } },
  "expires_at": "2026-10-24T22:15:00Z",
  "price": { "...": "price object above" },
  "payment": null,
  "created_at": "2026-10-24T22:00:00Z"
}
```

`payment` is `null` or `{ "status", "provider", "amount" }`.

`POST /api/bookings` (guest or staff)
Header: `Idempotency-Key: <opaque string>` (optional). Body: `{ "room_type_id", "check_in", "check_out", "guests" }`.
The server picks a free room of that type and inserts the booking; the database constraint is the final arbiter. If another request wins the race for the same room, the next candidate room is tried; if none remains, `409 no_availability`.
Returns `201` with the booking. Replaying the same `Idempotency-Key` for the same user returns `200` with the original booking and creates nothing.

`GET /api/bookings` (guest: own bookings; staff: all bookings, optional `?status=`) returns `{ "items": [booking] }`, newest first.

`GET /api/bookings/{id}` (owner or staff) returns the booking. `404` if it is not yours (guests never learn that other bookings exist).

`DELETE /api/bookings/{id}` (owner or staff) cancels a `PENDING` or `CONFIRMED` booking whose `check_in` is today or later. Returns `200` with the booking (`status: CANCELLED`). `409 invalid_state` otherwise.

### Payments

`POST /api/bookings/{id}/pay` (owner) starts payment for a `PENDING`, unexpired booking.

- provider `stripe`: creates a Stripe PaymentIntent in test mode. Returns `200 { "provider": "stripe", "client_secret": "...", "amount": "2940.00", "currency": "MAD" }`.
- provider `mock`: returns `200 { "provider": "mock", "amount": "...", "currency": "MAD" }`. Used when no Stripe key is configured (public demo, tests).

`POST /api/payments/mock/confirm` (owner) body `{ "booking_id" }`. Only available when provider is `mock` (otherwise `404`). Builds the same event object a Stripe webhook would deliver and feeds it to the same handler, so the booking becomes `CONFIRMED`.

`POST /api/payments/webhook` (Stripe only, no JWT)
Verifies the `Stripe-Signature` header with `STRIPE_WEBHOOK_SECRET` (`400` on a bad signature). Handles `payment_intent.succeeded` (booking `CONFIRMED`, payment `SUCCEEDED`) and `payment_intent.payment_failed` (payment `FAILED`, booking stays `PENDING` until its hold expires). Each `event.id` is stored in `webhook_events`; a duplicate event is acknowledged with `200` and has no effect. A success event arriving for an `EXPIRED` or `CANCELLED` booking is logged and ignored. The webhook is the only way a booking becomes `CONFIRMED`.

### Back office (staff only)

`GET /api/rooms` returns `{ "items": [ { "id", "number", "status", "room_type": { "id", "label", "base_price", "capacity" } } ] }`.

`PUT /api/rooms/{id}` body: any of `{ "number", "status" }`. Returns the room.

`PUT /api/room-types/{id}` body: any of `{ "label", "description", "base_price", "capacity" }`. Returns the room type.

`POST /api/room-types/{id}/rates` body `{ "start", "end", "price" }` (end exclusive). Returns `201` with the rate. `409 invalid_state` when the season overlaps an existing rate.

`GET /api/room-types/{id}/rates` returns `{ "items": [ { "id", "start", "end", "price" } ] }`.

## Implementation notes (where the code refines this contract)

- `bookings` has an extra nullable JSONB column `price` that freezes the price breakdown at booking time, so later rate changes never alter an existing booking. The API shape is unchanged.
- `?status=` filtering on `GET /api/bookings` works for guests as well as staff. An unknown status returns `422`.
- `POST /api/bookings/{id}/pay` and `POST /api/payments/mock/confirm` are owner-only: staff get `404` on other people's bookings.
- `POST /api/payments/webhook` returns `404` when `STRIPE_WEBHOOK_SECRET` is not configured, and `400 validation_error` on a bad signature.
- A success event for a `PENDING` booking whose hold has passed but has not yet been swept is accepted as `CONFIRMED` (the money was taken). Only `EXPIRED` and `CANCELLED` bookings ignore it.
- `JWT_SECRET` is required by every process that builds the app (including `flask db upgrade` and `seed`) outside tests.
- The OpenAPI spec is hand-written; a test checks that every `/api` route is listed. The Swagger UI page loads its assets from a CDN.

## Demo data (`flask --app wsgi seed`)

Idempotent. Creates:

| Room type | Rooms | Base price (MAD / night) | Capacity |
|---|---|---|---|
| Standard | 101 to 104 | 700 | 2 |
| Deluxe | 201 to 203 | 1100 | 3 |
| Riad Suite | 301 (a single room) | 2200 | 4 |

Seasonal rates for each type (high season +25%, e.g. 2026-03-01 to 2026-06-01 and 2026-09-01 to 2026-11-01), and two accounts: `guest@demo.test` and `staff@demo.test`, both with password `demo1234`.

## Frontend routes

| Route | Page |
|---|---|
| `/` | Search form (dates, guests) and results |
| `/book` | Booking summary and confirmation (requires login, redirects to `/login` then back) |
| `/bookings/:id/pay` | Payment step with hold countdown |
| `/bookings` | My bookings, cancel |
| `/login`, `/register` | Auth |
| `/staff` | Rooms list, status and price edits (staff only) |

Language switcher (fr / en) in the header; language persisted in `localStorage` with a try/catch.
