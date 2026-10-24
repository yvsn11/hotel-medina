"""Pure pricing functions (no Flask, no database)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CURRENCY = "MAD"
CENT = Decimal("0.01")
DISCOUNT_4_TO_6 = Decimal("0.05")
DISCOUNT_7_PLUS = Decimal("0.10")


@dataclass(frozen=True)
class Season:
    """A seasonal rate; `end` is exclusive."""

    start: date
    end: date
    price: Decimal


@dataclass(frozen=True)
class Price:
    nights: int
    nightly_avg: Decimal
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    currency: str = CURRENCY

    def to_dict(self) -> dict[str, Any]:
        return {
            "nights": self.nights,
            "nightly_avg": money(self.nightly_avg),
            "subtotal": money(self.subtotal),
            "discount": money(self.discount),
            "tax": money(self.tax),
            "total": money(self.total),
            "currency": self.currency,
        }


def quantize(value: Decimal) -> Decimal:
    """Round half-up to 2 decimals."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def money(value: Decimal) -> str:
    """Serialize an amount as a string with exactly 2 decimals."""
    return format(quantize(value), "f")


def count_nights(check_in: date, check_out: date) -> int:
    return (check_out - check_in).days


def nightly_price(day: date, base_price: Decimal, seasons: Sequence[Season]) -> Decimal:
    for season in seasons:
        if season.start <= day < season.end:
            return quantize(season.price)
    return quantize(base_price)


def discount_rate(nights: int) -> Decimal:
    if nights >= 7:
        return DISCOUNT_7_PLUS
    if nights >= 4:
        return DISCOUNT_4_TO_6
    return Decimal(0)


def compute_price(
    check_in: date,
    check_out: date,
    base_price: Decimal,
    seasons: Sequence[Season],
    guests: int,
    tax_per_person_night: Decimal,
) -> Price:
    nights = count_nights(check_in, check_out)
    if nights < 1:
        raise ValueError("a stay must have at least one night")
    if guests < 1:
        raise ValueError("a stay needs at least one guest")

    subtotal = sum(
        (nightly_price(check_in + timedelta(days=i), base_price, seasons) for i in range(nights)),
        Decimal(0),
    )
    subtotal = quantize(subtotal)
    discount = quantize(subtotal * discount_rate(nights))
    tax = quantize(tax_per_person_night * guests * nights)
    total = subtotal - discount + tax
    return Price(
        nights=nights,
        nightly_avg=quantize(subtotal / nights),
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        total=quantize(total),
    )
