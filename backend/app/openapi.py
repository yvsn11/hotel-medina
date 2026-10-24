"""Hand-maintained OpenAPI 3 description of the API (kept in sync by a test)."""

from __future__ import annotations

from typing import Any

Json = dict[str, Any]

_ERR = {"$ref": "#/components/schemas/Error"}


def _resp(description: str, schema: str | None = None) -> Json:
    out: Json = {"description": description}
    if schema:
        out["content"] = {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{schema}"}}
        }
    return out


def _errors(*codes: int) -> Json:
    names = {
        400: "Malformed input or bad signature",
        401: "Missing or invalid token",
        403: "Role not allowed",
        404: "Not found",
        409: "Conflict",
        422: "Validation error",
    }
    return {
        str(c): {"description": names[c], "content": {"application/json": {"schema": _ERR}}}
        for c in codes
    }


def _body(schema: str) -> Json:
    return {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema}"}}},
    }


def _op(
    summary: str,
    tag: str,
    ok: Json,
    *,
    secured: bool = False,
    body: str | None = None,
    params: list[Json] | None = None,
    errors: tuple[int, ...] = (),
) -> Json:
    op: Json = {"summary": summary, "tags": [tag], "responses": {**ok, **_errors(*errors)}}
    if secured:
        op["security"] = [{"bearerAuth": []}]
    if body:
        op["requestBody"] = _body(body)
    if params:
        op["parameters"] = params
    return op


def _path(name: str, description: str = "") -> Json:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": {"type": "integer"},
        "description": description,
    }


def _query(name: str, required: bool, typ: str = "string") -> Json:
    return {"name": name, "in": "query", "required": required, "schema": {"type": typ}}


def _obj(**props: Any) -> Json:
    return {"type": "object", "properties": {k: v for k, v in props.items()}}


_S = {"type": "string"}
_I = {"type": "integer"}


def build_spec() -> Json:
    id_param = [_path("booking_id")]
    paths: Json = {
        "/api/health": {"get": _op("Health check (database)", "Health", _resp("ok"), errors=())},
        "/api/auth/register": {
            "post": _op(
                "Register a guest",
                "Auth",
                {"201": _resp("Created", "AuthResponse")},
                body="Register",
                errors=(409, 422),
            )
        },
        "/api/auth/login": {
            "post": _op(
                "Log in",
                "Auth",
                {"200": _resp("OK", "AuthResponse")},
                body="Login",
                errors=(401, 422),
            )
        },
        "/api/rooms/available": {
            "get": _op(
                "Search available room types",
                "Availability",
                {"200": _resp("OK", "AvailabilityResponse")},
                params=[
                    _query("from", True),
                    _query("to", True),
                    _query("guests", False, "integer"),
                ],
                errors=(422,),
            )
        },
        "/api/bookings": {
            "post": _op(
                "Create a booking (Idempotency-Key header optional)",
                "Bookings",
                {"201": _resp("Created", "Booking"), "200": _resp("Idempotent replay", "Booking")},
                secured=True,
                body="BookingCreate",
                params=[
                    {"name": "Idempotency-Key", "in": "header", "required": False, "schema": _S}
                ],
                errors=(401, 404, 409, 422),
            ),
            "get": _op(
                "List bookings (guest: own, staff: all)",
                "Bookings",
                {"200": _resp("OK", "BookingList")},
                secured=True,
                params=[_query("status", False)],
                errors=(401, 422),
            ),
        },
        "/api/bookings/{booking_id}": {
            "get": _op(
                "Get a booking",
                "Bookings",
                {"200": _resp("OK", "Booking")},
                secured=True,
                params=id_param,
                errors=(401, 404),
            ),
            "delete": _op(
                "Cancel a booking",
                "Bookings",
                {"200": _resp("Cancelled", "Booking")},
                secured=True,
                params=id_param,
                errors=(401, 404, 409),
            ),
        },
        "/api/bookings/{booking_id}/pay": {
            "post": _op(
                "Start payment",
                "Payments",
                {"200": _resp("OK", "PaymentStart")},
                secured=True,
                params=id_param,
                errors=(401, 404, 409),
            ),
        },
        "/api/payments/mock/confirm": {
            "post": _op(
                "Confirm a mock payment",
                "Payments",
                {"200": _resp("OK", "Booking")},
                secured=True,
                body="MockConfirm",
                errors=(401, 404, 409, 422),
            ),
        },
        "/api/payments/webhook": {
            "post": _op(
                "Stripe webhook (signature verified)",
                "Payments",
                {"200": _resp("Acknowledged")},
                errors=(400, 404),
            ),
        },
        "/api/rooms": {
            "get": _op(
                "List rooms (staff)",
                "Back office",
                {"200": _resp("OK")},
                secured=True,
                errors=(401, 403),
            ),
        },
        "/api/rooms/{room_id}": {
            "put": _op(
                "Update a room (staff)",
                "Back office",
                {"200": _resp("OK")},
                secured=True,
                body="RoomUpdate",
                params=[_path("room_id")],
                errors=(401, 403, 404, 409, 422),
            ),
        },
        "/api/room-types/{room_type_id}": {
            "put": _op(
                "Update a room type (staff)",
                "Back office",
                {"200": _resp("OK")},
                secured=True,
                body="RoomTypeUpdate",
                params=[_path("room_type_id")],
                errors=(401, 403, 404, 422),
            ),
        },
        "/api/room-types/{room_type_id}/rates": {
            "get": _op(
                "List seasonal rates (staff)",
                "Back office",
                {"200": _resp("OK")},
                secured=True,
                params=[_path("room_type_id")],
                errors=(401, 403, 404),
            ),
            "post": _op(
                "Add a seasonal rate (staff)",
                "Back office",
                {"201": _resp("Created")},
                secured=True,
                body="RateCreate",
                params=[_path("room_type_id")],
                errors=(401, 403, 404, 409, 422),
            ),
        },
    }
    price = _obj(nights=_I, nightly_avg=_S, subtotal=_S, discount=_S, tax=_S, total=_S, currency=_S)
    schemas: Json = {
        "Error": _obj(error=_S, message=_S, details={"type": "object"}),
        "User": _obj(
            id=_I, email=_S, full_name=_S, role={"type": "string", "enum": ["guest", "staff"]}
        ),
        "AuthResponse": _obj(token=_S, user={"$ref": "#/components/schemas/User"}),
        "Register": {
            **_obj(email=_S, password={"type": "string", "minLength": 8}, full_name=_S),
            "required": ["email", "password", "full_name"],
        },
        "Login": {**_obj(email=_S, password=_S), "required": ["email", "password"]},
        "Price": price,
        "AvailabilityResponse": _obj(
            **{"from": _S},
            to=_S,
            guests=_I,
            items={
                "type": "array",
                "items": _obj(
                    room_type={"type": "object"},
                    available_rooms=_I,
                    price={"$ref": "#/components/schemas/Price"},
                ),
            },
        ),
        "BookingCreate": {
            **_obj(room_type_id=_I, check_in=_S, check_out=_S, guests=_I),
            "required": ["room_type_id", "check_in", "check_out", "guests"],
        },
        "Booking": _obj(
            id=_I,
            status={"type": "string", "enum": ["PENDING", "CONFIRMED", "CANCELLED", "EXPIRED"]},
            check_in=_S,
            check_out=_S,
            nights=_I,
            guests=_I,
            room={"type": "object"},
            expires_at={"type": "string", "nullable": True},
            price={"$ref": "#/components/schemas/Price"},
            payment={"type": "object", "nullable": True},
            created_at=_S,
        ),
        "BookingList": _obj(
            items={"type": "array", "items": {"$ref": "#/components/schemas/Booking"}}
        ),
        "PaymentStart": _obj(provider=_S, client_secret=_S, amount=_S, currency=_S),
        "MockConfirm": {**_obj(booking_id=_I), "required": ["booking_id"]},
        "RoomUpdate": _obj(
            number=_S, status={"type": "string", "enum": ["AVAILABLE", "MAINTENANCE"]}
        ),
        "RoomTypeUpdate": _obj(label=_S, description=_S, base_price=_S, capacity=_I),
        "RateCreate": {**_obj(start=_S, end=_S, price=_S), "required": ["start", "end", "price"]},
    }
    return {
        "openapi": "3.0.3",
        "info": {"title": "Hotel Medina API", "version": "1.0.0"},
        "paths": paths,
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            },
            "schemas": schemas,
        },
    }
