from dataclasses import dataclass
from enum import StrEnum
from typing import Final


DOMAIN: Final = "solar_mind"

CONF_BATTERY_CAPACITY: Final = "battery_capacity"
CONF_MAX_PV_POWER: Final = "max_pv_power"
CONF_AVERAGE_HOUSE_LOAD: Final = "average_house_load"
CONF_BATTERY_EFFICIENCY: Final = "battery_efficiency"
CONF_PV_AZIMUTH: Final = "pv_azimuth"
CONF_PV_TILT: Final = "pv_tilt"

CONF_PRICE_MODE: Final = "price_mode"
CONF_PRICE_SENSOR: Final = "price_sensor"
CONF_PRICE_SOURCE: Final = "price_source"
CONF_FIXED_HIGH_PRICE: Final = "fixed_high_price"
CONF_FIXED_LOW_PRICE: Final = "fixed_low_price"


class PriceMode(StrEnum):
    """Pricing mode selection."""

    SPOT = "spot"
    FIXED = "fixed"

CONF_REMOTECONTROL_POWER_CONTROL: Final = "remotecontrol_power_control"
CONF_REMOTECONTROL_ACTIVE_POWER: Final = "remotecontrol_active_power"
CONF_REMOTECONTROL_TRIGGER: Final = "remotecontrol_trigger"

# Solax entity config keys
CONF_SOLAX_DEVICE_TYPE: Final = "solax_device_type"
CONF_REMOTECONTROL_POWER_CONTROL: Final = "remotecontrol_power_control"
CONF_REMOTECONTROL_ACTIVE_POWER: Final = "remotecontrol_active_power"
CONF_REMOTECONTROL_TRIGGER: Final = "remotecontrol_trigger"
CONF_REMOTECONTROL_AUTOREPEAT_DURATION: Final = "remotecontrol_autorepeat_duration"
CONF_BATTERY_SOC: Final = "battery_soc"


class SystemStatus(StrEnum):
    """System status values."""

    CHARGING = "charging"
    CHARGING_TO_SOC = "charging_to_soc"
    DISCHARGING = "discharging"
    SELF_USE = "self_use"
    HOUSE_FROM_GRID = "house_from_grid"
    IDLE = "idle"
    ERROR = "error"

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