from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.pricing import (
    Season,
    compute_price,
    discount_rate,
    money,
    nightly_price,
    quantize,
)

TAX = Decimal("15.00")
D0 = date(2026, 12, 1)

prices = st.decimals(min_value=0, max_value=100000, places=2, allow_nan=False, allow_infinity=False)
tax_rates = st.decimals(min_value=0, max_value=200, places=2, allow_nan=False, allow_infinity=False)
guests_st = st.integers(min_value=1, max_value=6)
nights_st = st.integers(min_value=1, max_value=30)
start_dates = st.dates(min_value=date(2026, 1, 1), max_value=date(2028, 12, 31))


@st.composite
def seasons_st(draw: st.DrawFn) -> list[Season]:
    """A few non-overlapping seasons around the stay."""
    cursor = draw(start_dates)
    seasons = []
    for _ in range(draw(st.integers(0, 3))):
        start = cursor + timedelta(days=draw(st.integers(0, 20)))
        end = start + timedelta(days=draw(st.integers(1, 40)))
        seasons.append(Season(start, end, draw(prices)))
        cursor = end
    return seasons


@given(start_dates, nights_st, prices, seasons_st(), guests_st, tax_rates)
def test_total_is_never_negative(
    start: date, nights: int, base: Decimal, seasons: list[Season], guests: int, tax: Decimal
) -> None:
    price = compute_price(start, start + timedelta(days=nights), base, seasons, guests, tax)
    assert price.total >= 0
    assert price.subtotal >= 0
    assert 0 <= price.discount <= price.subtotal
    assert price.total == price.subtotal - price.discount + price.tax


@given(start_dates, nights_st, st.integers(1, 10), prices, guests_st, tax_rates)
def test_longer_stay_never_has_lower_subtotal_for_constant_rate(
    start: date, nights: int, extra: int, base: Decimal, guests: int, tax: Decimal
) -> None:
    short = compute_price(start, start + timedelta(days=nights), base, [], guests, tax)
    long = compute_price(start, start + timedelta(days=nights + extra), base, [], guests, tax)
    assert long.subtotal >= short.subtotal
    assert long.tax >= short.tax


@given(start_dates, nights_st, prices, guests_st, tax_rates)
def test_tax_is_not_discounted(
    start: date, nights: int, base: Decimal, guests: int, tax_rate: Decimal
) -> None:
    price = compute_price(start, start + timedelta(days=nights), base, [], guests, tax_rate)
    expected_tax = (tax_rate * guests * nights).quantize(Decimal("0.01"), ROUND_HALF_UP)
    assert price.tax == expected_tax
    assert price.total - price.tax == price.subtotal - price.discount


@given(start_dates, nights_st, prices, seasons_st(), guests_st, tax_rates)
def test_amounts_have_two_decimals_and_nights_match(
    start: date, nights: int, base: Decimal, seasons: list[Season], guests: int, tax: Decimal
) -> None:
    price = compute_price(start, start + timedelta(days=nights), base, seasons, guests, tax)
    assert price.nights == nights
    for amount in (price.nightly_avg, price.subtotal, price.discount, price.tax, price.total):
        assert amount == amount.quantize(Decimal("0.01"))
        assert len(money(amount).split(".")[1]) == 2


@given(st.decimals(min_value=0, max_value=10**6, places=4, allow_nan=False, allow_infinity=False))
def test_rounding_is_half_up(value: Decimal) -> None:
    rounded = quantize(value)
    assert abs(rounded - value) <= Decimal("0.005")
    assert rounded == value.quantize(Decimal("0.01"), ROUND_HALF_UP)


def test_half_cents_round_up_not_to_even() -> None:
    assert quantize(Decimal("0.125")) == Decimal("0.13")
    assert quantize(Decimal("0.135")) == Decimal("0.14")
    assert quantize(Decimal("2.675")) == Decimal("2.68")
    assert money(Decimal("5")) == "5.00"


def test_spec_example_three_nights() -> None:
    price = compute_price(D0, D0 + timedelta(days=3), Decimal("950"), [], 2, Decimal("15.00"))
    assert price.to_dict() == {
        "nights": 3,
        "nightly_avg": "950.00",
        "subtotal": "2850.00",
        "discount": "0.00",
        "tax": "90.00",
        "total": "2940.00",
        "currency": "MAD",
    }


@pytest.mark.parametrize(
    ("nights", "rate"),
    [(1, "0"), (3, "0"), (4, "0.05"), (6, "0.05"), (7, "0.10"), (30, "0.10")],
)
def test_discount_tiers(nights: int, rate: str) -> None:
    assert discount_rate(nights) == Decimal(rate)


def test_five_percent_discount_for_four_nights() -> None:
    price = compute_price(D0, D0 + timedelta(days=4), Decimal("700"), [], 2, TAX)
    assert price.subtotal == Decimal("2800.00")
    assert price.discount == Decimal("140.00")
    assert price.tax == Decimal("120.00")
    assert price.total == Decimal("2780.00")


def test_ten_percent_discount_for_seven_nights() -> None:
    price = compute_price(D0, D0 + timedelta(days=7), Decimal("700"), [], 1, TAX)
    assert price.subtotal == Decimal("4900.00")
    assert price.discount == Decimal("490.00")
    assert price.tax == Decimal("105.00")
    assert price.total == Decimal("4515.00")


def test_discount_is_rounded_half_up() -> None:
    # 4 nights of 100.10 -> subtotal 400.40, 5% = 20.020 -> 20.02
    price = compute_price(D0, D0 + timedelta(days=4), Decimal("100.10"), [], 1, Decimal(0))
    assert price.subtotal == Decimal("400.40")
    assert price.discount == Decimal("20.02")


def test_discount_half_cent_rounds_up() -> None:
    # subtotal 400.10 * 5% = 20.0050 exactly -> 20.01 with half-up (half-even would give 20.00)
    seasons = [
        Season(D0, D0 + timedelta(days=1), Decimal("100.10")),
        Season(D0 + timedelta(days=1), D0 + timedelta(days=4), Decimal("100.00")),
    ]
    price = compute_price(D0, D0 + timedelta(days=4), Decimal("1"), seasons, 1, Decimal(0))
    assert price.subtotal == Decimal("400.10")
    assert price.discount == Decimal("20.01")


def test_seasonal_rate_applies_to_nights_inside_the_season_only() -> None:
    # Season is [Dec 2, Dec 4): nights of Dec 2 and Dec 3 are high season.
    season = Season(date(2026, 12, 2), date(2026, 12, 4), Decimal("875.00"))
    price = compute_price(D0, date(2026, 12, 5), Decimal("700"), [season], 1, Decimal(0))
    assert price.nights == 4
    assert price.subtotal == Decimal("700") + 2 * Decimal("875") + Decimal("700")
    assert nightly_price(date(2026, 12, 4), Decimal("700"), [season]) == Decimal("700.00")
    assert nightly_price(date(2026, 12, 3), Decimal("700"), [season]) == Decimal("875.00")


def test_stay_entirely_in_season_uses_the_season_price() -> None:
    season = Season(date(2026, 9, 1), date(2026, 11, 1), Decimal("875"))
    price = compute_price(date(2026, 10, 24), date(2026, 10, 27), Decimal("700"), [season], 2, TAX)
    assert price.subtotal == Decimal("2625.00")
    assert price.nightly_avg == Decimal("875.00")


def test_stay_outside_every_season_uses_the_base_price() -> None:
    season = Season(date(2026, 3, 1), date(2026, 6, 1), Decimal("875"))
    price = compute_price(D0, D0 + timedelta(days=2), Decimal("700"), [season], 1, TAX)
    assert price.subtotal == Decimal("1400.00")


def test_season_end_is_exclusive() -> None:
    season = Season(date(2026, 10, 1), date(2026, 11, 1), Decimal("875"))
    # Night of Oct 31 is high season, the night of Nov 1 is not.
    price = compute_price(
        date(2026, 10, 31), date(2026, 11, 2), Decimal("700"), [season], 1, Decimal(0)
    )
    assert price.subtotal == Decimal("1575.00")


@pytest.mark.parametrize(("nights", "guests"), [(0, 1), (-2, 1), (2, 0)])
def test_invalid_stays_are_rejected(nights: int, guests: int) -> None:
    with pytest.raises(ValueError, match="at least one"):
        compute_price(D0, D0 + timedelta(days=nights), Decimal("700"), [], guests, TAX)
