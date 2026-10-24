"""Request validation (pydantic) and the helper that parses a request body."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    ValidationError,
)

from app.errors import MalformedRequest, ValidationFailed
from app.models import RoomStatus
from app.services.users import EMAIL_RE

M = TypeVar("M", bound=BaseModel)


def _email(value: str) -> str:
    if not EMAIL_RE.match(value) or len(value) > 255:
        raise ValueError("must be a valid email address")
    return value


Email = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_email)]
Money = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RegisterIn(Schema):
    email: Email
    password: Annotated[str, Field(min_length=8, max_length=128)]
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]


class LoginIn(Schema):
    email: Email
    password: Annotated[str, Field(min_length=1, max_length=128)]


class BookingIn(Schema):
    room_type_id: StrictInt
    check_in: date
    check_out: date
    guests: Annotated[StrictInt, Field(ge=1, le=6)]


class AvailabilityQuery(Schema):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    from_: date = Field(alias="from")
    to: date
    guests: Annotated[int, Field(ge=1, le=6)] = 1


class MockConfirmIn(Schema):
    booking_id: StrictInt


class RoomUpdate(Schema):
    number: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)] | None
    ) = None
    status: RoomStatus | None = None


class RoomTypeUpdate(Schema):
    label: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    description: Annotated[str, Field(max_length=2000)] | None = None
    base_price: Money | None = None
    capacity: Annotated[StrictInt, Field(ge=1, le=20)] | None = None


class RateIn(Schema):
    start: date
    end: date
    price: Money


def validate(model: type[M], data: Any) -> M:
    if not isinstance(data, dict):
        raise MalformedRequest("The request body must be a JSON object")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "body"
            fields[loc] = err["msg"]
        raise ValidationFailed("Invalid request", {"fields": fields}) from exc
