"""Data models for the Solar Mind integration."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .types import Energy, Timeseries



@dataclass
class HourlyPrice:
    """Represents a single hourly price point."""

    start: datetime
    price: float

    def __post_init__(self) -> None:
        """Validate after initialization."""
        if not isinstance(self.start, datetime):
            raise ValueError("start must be a datetime object")


@dataclass
class PriceData:
    """Normalized price data from any source."""

    today: list[HourlyPrice] = field(default_factory=list)
    tomorrow: list[HourlyPrice] = field(default_factory=list)
    current_price: float | None = None
    tomorrow_available: bool = False

    def get_price_at(self, dt: datetime) -> float | None:
        """Get price at a specific datetime."""
        for price in self.today + self.tomorrow:
            if price.start <= dt < price.start.replace(
                hour=price.start.hour + 1 if price.start.hour < 23 else 0
            ):
                return price.price
        return None

    def get_cheapest_hours(self, n: int = 6) -> list[HourlyPrice]:
        """Get the N cheapest hours from today and tomorrow."""
        all_prices = sorted(self.today + self.tomorrow, key=lambda x: x.price)
        return all_prices[:n]



@dataclass
class SolarMindData:
    """Coordinator data container."""

    prices: PriceData = field(default_factory=PriceData)
    
    last_update: datetime | None = None
    last_error: str | None = None
   
    generation_forecast: Timeseries[Energy] | None = None