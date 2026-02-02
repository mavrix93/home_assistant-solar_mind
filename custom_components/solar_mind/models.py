"""Data models for the Solar Mind integration."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .const import StrategyKey, SystemStatus


class PlannedAction(str, Enum):
    """Planned action for an hour."""
    
    CHARGE = "charge"
    DISCHARGE = "discharge"
    SELF_USE = "self_use"
    IDLE = "idle"


@dataclass
class HourlyPlanEntry:
    """Represents a single hour in the energy plan."""
    
    hour: datetime
    # Planned action
    action: PlannedAction
    # Forecasts
    pv_forecast_wh: float  # Expected PV generation (Wh)
    load_forecast_wh: float  # Expected house load (Wh)
    price: float | None  # Spot price for this hour
    # Planned values
    planned_grid_import_wh: float  # Energy to import from grid (Wh)
    planned_grid_export_wh: float  # Energy to export to grid (Wh)
    planned_battery_charge_wh: float  # Energy to charge battery (Wh)
    planned_battery_discharge_wh: float  # Energy to discharge from battery (Wh)
    # State at end of hour
    predicted_soc: float  # Predicted battery SOC at end of hour (%)
    # Metadata
    solar_potential: float  # 0.0-1.0 scale
    weather_condition: str
    reason: str  # Why this action was chosen

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hour": self.hour.isoformat(),
            "action": self.action.value,
            "pv_forecast_wh": round(self.pv_forecast_wh, 1),
            "load_forecast_wh": round(self.load_forecast_wh, 1),
            "price": round(self.price, 4) if self.price else None,
            "planned_grid_import_wh": round(self.planned_grid_import_wh, 1),
            "planned_grid_export_wh": round(self.planned_grid_export_wh, 1),
            "planned_battery_charge_wh": round(self.planned_battery_charge_wh, 1),
            "planned_battery_discharge_wh": round(self.planned_battery_discharge_wh, 1),
            "predicted_soc": round(self.predicted_soc, 1),
            "solar_potential": round(self.solar_potential, 2),
            "weather_condition": self.weather_condition,
            "reason": self.reason,
        }


@dataclass
class EnergyPlan:
    """Complete energy plan for the forecast period (24-48 hours)."""
    
    created_at: datetime
    entries: list[HourlyPlanEntry] = field(default_factory=list)
    # Summary statistics
    total_pv_forecast_wh: float = 0.0
    total_load_forecast_wh: float = 0.0
    total_grid_import_wh: float = 0.0
    total_grid_export_wh: float = 0.0
    estimated_cost: float = 0.0
    estimated_revenue: float = 0.0
    
    def get_entry_at(self, dt: datetime) -> HourlyPlanEntry | None:
        """Get plan entry for a specific hour."""
        for entry in self.entries:
            if entry.hour <= dt < entry.hour + timedelta(hours=1):
                return entry
        return None
    
    def get_next_charge_hours(self, n: int = 6) -> list[HourlyPlanEntry]:
        """Get next N hours where charging is planned."""
        return [e for e in self.entries if e.action == PlannedAction.CHARGE][:n]
    
    def get_next_discharge_hours(self, n: int = 6) -> list[HourlyPlanEntry]:
        """Get next N hours where discharging is planned."""
        return [e for e in self.entries if e.action == PlannedAction.DISCHARGE][:n]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "created_at": self.created_at.isoformat(),
            "entries": [e.to_dict() for e in self.entries],
            "total_pv_forecast_wh": round(self.total_pv_forecast_wh, 1),
            "total_load_forecast_wh": round(self.total_load_forecast_wh, 1),
            "total_grid_import_wh": round(self.total_grid_import_wh, 1),
            "total_grid_export_wh": round(self.total_grid_export_wh, 1),
            "estimated_cost": round(self.estimated_cost, 2),
            "estimated_revenue": round(self.estimated_revenue, 2),
        }


@dataclass
class HourlyActual:
    """Actual values recorded for an hour (for comparison with predictions)."""
    
    hour: datetime
    action_taken: PlannedAction | None
    pv_actual_wh: float | None
    load_actual_wh: float | None
    grid_import_actual_wh: float | None
    grid_export_actual_wh: float | None
    battery_soc_end: float | None
    price_actual: float | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hour": self.hour.isoformat(),
            "action_taken": self.action_taken.value if self.action_taken else None,
            "pv_actual_wh": round(self.pv_actual_wh, 1) if self.pv_actual_wh else None,
            "load_actual_wh": round(self.load_actual_wh, 1) if self.load_actual_wh else None,
            "grid_import_actual_wh": round(self.grid_import_actual_wh, 1) if self.grid_import_actual_wh else None,
            "grid_export_actual_wh": round(self.grid_export_actual_wh, 1) if self.grid_export_actual_wh else None,
            "battery_soc_end": round(self.battery_soc_end, 1) if self.battery_soc_end else None,
            "price_actual": round(self.price_actual, 4) if self.price_actual else None,
        }


@dataclass
class PredictionComparison:
    """Comparison between predicted and actual values for an hour."""
    
    hour: datetime
    predicted: HourlyPlanEntry | None
    actual: HourlyActual | None
    
    @property
    def pv_error_wh(self) -> float | None:
        """PV forecast error (actual - predicted)."""
        if self.predicted and self.actual and self.actual.pv_actual_wh is not None:
            return self.actual.pv_actual_wh - self.predicted.pv_forecast_wh
        return None
    
    @property
    def load_error_wh(self) -> float | None:
        """Load forecast error (actual - predicted)."""
        if self.predicted and self.actual and self.actual.load_actual_wh is not None:
            return self.actual.load_actual_wh - self.predicted.load_forecast_wh
        return None
    
    @property
    def soc_error_pct(self) -> float | None:
        """SOC prediction error (actual - predicted)."""
        if self.predicted and self.actual and self.actual.battery_soc_end is not None:
            return self.actual.battery_soc_end - self.predicted.predicted_soc
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hour": self.hour.isoformat(),
            "predicted": self.predicted.to_dict() if self.predicted else None,
            "actual": self.actual.to_dict() if self.actual else None,
            "pv_error_wh": round(self.pv_error_wh, 1) if self.pv_error_wh is not None else None,
            "load_error_wh": round(self.load_error_wh, 1) if self.load_error_wh is not None else None,
            "soc_error_pct": round(self.soc_error_pct, 1) if self.soc_error_pct is not None else None,
        }


@dataclass
class PlanHistory:
    """Historical predictions and actuals for accuracy tracking."""
    
    # Store last N hours of comparisons
    comparisons: list[PredictionComparison] = field(default_factory=list)
    max_entries: int = 168  # 7 days of hourly data
    
    def add_comparison(self, comparison: PredictionComparison) -> None:
        """Add a comparison, removing old entries if needed."""
        self.comparisons.append(comparison)
        if len(self.comparisons) > self.max_entries:
            self.comparisons = self.comparisons[-self.max_entries:]
    
    def get_recent(self, hours: int = 24) -> list[PredictionComparison]:
        """Get recent comparisons."""
        return self.comparisons[-hours:] if self.comparisons else []
    
    @property
    def pv_forecast_accuracy(self) -> float | None:
        """Calculate PV forecast accuracy (MAPE) for recent predictions."""
        errors = []
        for c in self.comparisons[-24:]:
            if c.predicted and c.actual and c.actual.pv_actual_wh is not None:
                if c.predicted.pv_forecast_wh > 0:
                    error = abs(c.pv_error_wh or 0) / c.predicted.pv_forecast_wh
                    errors.append(error)
        if not errors:
            return None
        return (1 - sum(errors) / len(errors)) * 100
    
    @property
    def load_forecast_accuracy(self) -> float | None:
        """Calculate load forecast accuracy (MAPE) for recent predictions."""
        errors = []
        for c in self.comparisons[-24:]:
            if c.predicted and c.actual and c.actual.load_actual_wh is not None:
                if c.predicted.load_forecast_wh > 0:
                    error = abs(c.load_error_wh or 0) / c.predicted.load_forecast_wh
                    errors.append(error)
        if not errors:
            return None
        return (1 - sum(errors) / len(errors)) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "comparisons": [c.to_dict() for c in self.comparisons],
            "pv_forecast_accuracy": round(self.pv_forecast_accuracy, 1) if self.pv_forecast_accuracy else None,
            "load_forecast_accuracy": round(self.load_forecast_accuracy, 1) if self.load_forecast_accuracy else None,
        }


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
    # Energy plan and history
    energy_plan: EnergyPlan | None = None
    plan_history: PlanHistory = field(default_factory=PlanHistory)
    # System config for planning (from options)
    battery_capacity_wh: float = 10000.0
    max_pv_power_w: float = 10000.0