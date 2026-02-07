"""Types for Solar Mind – platform-agnostic time series and plan actions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class PlanAction(StrEnum):
    """Planned action for an hour – output of SolarMind.create_plan."""

    CHARGE = "CHARGE"           # Charge battery (e.g. from grid or surplus)
    SELL = "SELL"               # Export to grid (discharge or surplus)
    BATTERY_USE = "BATTERY_USE" # Use battery for house load
    GRID_USE = "GRID_USE"       # Use grid for house load


@dataclass(frozen=True)
class Timeseries(Generic[T]):
    """Time-indexed series of values (e.g. hourly). Points are (period start, value)."""

    points: list[tuple[datetime, T]]

    def get_at(self, dt: datetime) -> T | None:
        """Return value for the hour containing dt, or None."""
        for start, value in self.points:
            end = start + timedelta(hours=1)
            if start <= dt < end:
                return value
        return None

    def __iter__(self):
        return iter(self.points)


# Type aliases for create_plan inputs (values are simple scalars per hour)
Energy = float  # Wh for that hour
CloudCoverage = float  # 0.0–1.0 (e.g. 1 = clear, 0 = overcast)
Price = float  # Price per kWh for that hour


@dataclass(frozen=True)
class SolarMindConfig:
    """Configuration for SolarMind planning (no HA dependency)."""

    battery_capacity_wh: float = 14400.0
    min_soc: float = 10.0
    max_soc: float = 95.0
    max_pv_power_w: float = 10000.0
    average_house_load_wh: float = 500.0
    battery_efficiency: float = 0.90
    charge_price_threshold: float = 0.05
    discharge_price_threshold: float = 0.15
    charge_window_start: int = 22
    charge_window_end: int = 6
    discharge_allowed: bool = False
    max_charge_power_w: float = 3000.0
    max_discharge_power_w: float = 3000.0
    out_of_home_load_reduce_percent: float = 50.0
