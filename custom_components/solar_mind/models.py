"""Data models for the Solar Mind integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import StrategyKey, SystemStatus


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
class WeatherForecast:
    """Simplified weather forecast data."""

    hourly: list[dict[str, Any]] = field(default_factory=list)
    daily: list[dict[str, Any]] = field(default_factory=list)

    def get_solar_potential(self, hour: int) -> float:
        """
        Estimate solar potential for a given hour (0-1 scale).
        
        Based on weather condition and time of day.
        """
        for forecast in self.hourly:
            forecast_hour = forecast.get("datetime")
            if forecast_hour and isinstance(forecast_hour, datetime):
                if forecast_hour.hour == hour:
                    condition = forecast.get("condition", "").lower()
                    # Simple mapping of conditions to solar potential
                    if condition in ("sunny", "clear"):
                        return 1.0
                    elif condition in ("partlycloudy", "partly_cloudy"):
                        return 0.6
                    elif condition in ("cloudy",):
                        return 0.3
                    elif condition in ("rainy", "pouring", "snowy", "fog"):
                        return 0.1
                    return 0.5  # Unknown condition
        return 0.5  # Default


@dataclass
class SolaxState:
    """Current state from Solax entities."""

    battery_soc: float | None = None
    current_mode: str | None = None
    active_power: float | None = None
    grid_import: float | None = None
    grid_export: float | None = None
    house_load: float | None = None


@dataclass
class StrategyInput:
    """Input data for strategy computation."""

    current_time: datetime
    prices: PriceData
    weather: WeatherForecast
    solax_state: SolaxState
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyOutput:
    """Output from strategy computation."""

    status: SystemStatus
    mode: str  # Solax mode to set (e.g., "Enabled Grid Control")
    power_w: int | None = None  # Target power in watts (positive=charge, negative=discharge)
    duration_seconds: int | None = None  # Duration for autorepeat
    reason: str = ""  # Human-readable explanation

    @property
    def recommended_action(self) -> str:
        """Get human-readable recommended action."""
        if self.status == SystemStatus.CHARGING:
            power_str = f" at {self.power_w}W" if self.power_w else ""
            return f"Charge from grid{power_str}"
        elif self.status == SystemStatus.DISCHARGING:
            power_str = f" at {abs(self.power_w or 0)}W" if self.power_w else ""
            return f"Discharge to grid{power_str}"
        elif self.status == SystemStatus.SELF_USE:
            return "Self use (battery for house)"
        elif self.status == SystemStatus.HOUSE_FROM_GRID:
            return "House from grid (no discharge)"
        elif self.status == SystemStatus.IDLE:
            return "Idle"
        elif self.status == SystemStatus.ERROR:
            return f"Error: {self.reason}"
        return "Unknown"


@dataclass
class SolarMindData:
    """Coordinator data container."""

    prices: PriceData = field(default_factory=PriceData)
    weather: WeatherForecast = field(default_factory=WeatherForecast)
    solax_state: SolaxState = field(default_factory=SolaxState)
    strategy_output: StrategyOutput | None = None
    active_strategy: StrategyKey = StrategyKey.MANUAL
    last_update: datetime | None = None
    last_error: str | None = None
