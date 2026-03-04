"""Fixed two-tariff (high/low) price schedule for D57d distribution tariff.

All time windows are defined in **CET / CEST** (Europe/Prague).
Incoming datetimes are converted to that zone before evaluation.
"""

import zoneinfo
from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple

from .models import HourlyPrice, PriceData

_CET = zoneinfo.ZoneInfo("Europe/Prague")


class _TimeRange(NamedTuple):
    start: time
    end: time


# Low-tariff windows for D57d distribution tariff (CET).
# Hours NOT listed here are high-tariff.

_WORKDAY_LOW: list[_TimeRange] = [
    _TimeRange(time(0, 0), time(6, 15)),
    _TimeRange(time(7, 15), time(8, 15)),
    _TimeRange(time(9, 15), time(18, 15)),
    _TimeRange(time(19, 15), time(20, 15)),
    _TimeRange(time(21, 15), time(23, 59)),
]

_WEEKEND_LOW: list[_TimeRange] = [
    _TimeRange(time(0, 0), time(7, 45)),
    _TimeRange(time(8, 45), time(9, 45)),
    _TimeRange(time(10, 45), time(18, 15)),
    _TimeRange(time(19, 15), time(20, 15)),
    _TimeRange(time(21, 15), time(23, 59)),
]


def _is_weekend(d: date) -> bool:
    """Return True for Saturday (5) or Sunday (6)."""
    return d.weekday() >= 5


def _to_cet(dt: datetime) -> datetime:
    """Convert *dt* to Europe/Prague. Naive datetimes are assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CET)


def is_low_tariff(dt: datetime) -> bool:
    """Return True if *dt* falls inside a low-tariff window (evaluated in CET)."""
    cet_dt = _to_cet(dt)
    t = cet_dt.time()
    ranges = _WEEKEND_LOW if _is_weekend(cet_dt.date()) else _WORKDAY_LOW
    for r in ranges:
        if r.start <= t < r.end:
            return True
        # Handle the 23:59 boundary: 23:59 is the last minute of the day
        if r.end == time(23, 59) and t >= r.start:
            return True
    return False


def build_fixed_price_data(
    high_price: float,
    low_price: float,
    now: datetime | None = None,
) -> PriceData:
    """Build a PriceData with 24 hourly slots for today and tomorrow.

    Each hour is assigned *high_price* or *low_price* based on the
    hard-coded D57d timetable.  Hours are generated in CET (the zone the
    timetable is defined in) and then stored as UTC-aware datetimes so
    the rest of the system works uniformly.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    cet_now = _to_cet(now)
    today_cet = cet_now.date()
    tomorrow_cet = today_cet + timedelta(days=1)

    today_prices: list[HourlyPrice] = []
    tomorrow_prices: list[HourlyPrice] = []

    for hour in range(24):
        # Build CET-aware datetime, then convert to UTC for storage
        dt_today_cet = datetime(today_cet.year, today_cet.month, today_cet.day, hour, 0, tzinfo=_CET)
        price_today = low_price if is_low_tariff(dt_today_cet) else high_price
        today_prices.append(HourlyPrice(start=dt_today_cet.astimezone(timezone.utc), price=price_today))

        dt_tomorrow_cet = datetime(tomorrow_cet.year, tomorrow_cet.month, tomorrow_cet.day, hour, 0, tzinfo=_CET)
        price_tomorrow = low_price if is_low_tariff(dt_tomorrow_cet) else high_price
        tomorrow_prices.append(HourlyPrice(start=dt_tomorrow_cet.astimezone(timezone.utc), price=price_tomorrow))

    current_price = low_price if is_low_tariff(now) else high_price

    return PriceData(
        today=today_prices,
        tomorrow=tomorrow_prices,
        current_price=current_price,
        tomorrow_available=True,
    )
