"""Constants for the Solar Mind integration."""
from __future__ import annotations

from enum import Enum
from typing import Final

try:
    from enum import StrEnum
except ImportError:
    # Python < 3.11
    class StrEnum(str, Enum):
        """StrEnum compatibility for Python 3.9/3.10."""

        pass

DOMAIN: Final = "solar_mind"

# Config entry keys
CONF_PRICE_SENSOR: Final = "price_sensor"
CONF_PRICE_SOURCE: Final = "price_source"
CONF_WEATHER_ENTITY: Final = "weather_entity"
CONF_STRATEGY_SELECTOR_ENTITY: Final = "strategy_selector_entity"
CONF_FALLBACK_STRATEGY: Final = "fallback_strategy"

# Solax entity config keys
CONF_SOLAX_DEVICE_TYPE: Final = "solax_device_type"
CONF_ENERGY_STORAGE_MODE: Final = "energy_storage_mode"
CONF_REMOTECONTROL_POWER_CONTROL: Final = "remotecontrol_power_control"
CONF_REMOTECONTROL_ACTIVE_POWER: Final = "remotecontrol_active_power"
CONF_REMOTECONTROL_TRIGGER: Final = "remotecontrol_trigger"
CONF_REMOTECONTROL_AUTOREPEAT_DURATION: Final = "remotecontrol_autorepeat_duration"
CONF_BATTERY_SOC: Final = "battery_soc"

# Passive mode (Sofar) entity config keys
CONF_PASSIVE_DESIRED_GRID_POWER: Final = "passive_desired_grid_power"
CONF_PASSIVE_UPDATE_TRIGGER: Final = "passive_update_trigger"

# Options keys
CONF_CHARGE_PRICE_THRESHOLD: Final = "charge_price_threshold"
CONF_DISCHARGE_PRICE_THRESHOLD: Final = "discharge_price_threshold"
CONF_MIN_SOC: Final = "min_soc"
CONF_MAX_SOC: Final = "max_soc"
CONF_MAX_CHARGE_POWER: Final = "max_charge_power"
CONF_MAX_DISCHARGE_POWER: Final = "max_discharge_power"
CONF_CHARGE_WINDOW_START: Final = "charge_window_start"
CONF_CHARGE_WINDOW_END: Final = "charge_window_end"
CONF_DISCHARGE_ALLOWED: Final = "discharge_allowed"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_AUTOREPEAT_DURATION: Final = "autorepeat_duration"

# Default values
DEFAULT_CHARGE_PRICE_THRESHOLD: Final = 0.05  # EUR/kWh or CZK/kWh
DEFAULT_DISCHARGE_PRICE_THRESHOLD: Final = 0.15  # EUR/kWh or CZK/kWh
DEFAULT_MIN_SOC: Final = 10  # %
DEFAULT_MAX_SOC: Final = 95  # %
DEFAULT_MAX_CHARGE_POWER: Final = 3000  # W
DEFAULT_MAX_DISCHARGE_POWER: Final = 3000  # W
DEFAULT_CHARGE_WINDOW_START: Final = 22  # Hour (22:00)
DEFAULT_CHARGE_WINDOW_END: Final = 6  # Hour (06:00)
DEFAULT_DISCHARGE_ALLOWED: Final = False
DEFAULT_UPDATE_INTERVAL: Final = 5  # minutes
DEFAULT_AUTOREPEAT_DURATION: Final = 3600  # seconds (1 hour)


class PriceSource(StrEnum):
    """Price data source types."""

    CZECH_OTE = "czech_ote"
    NORD_POOL = "nord_pool"
    GENERIC = "generic"


class SolaxDeviceType(StrEnum):
    """Solax device control types."""

    MODBUS_REMOTE = "modbus_remote"
    PASSIVE_SOFAR = "passive_sofar"


class StrategyKey(StrEnum):
    """Strategy identifiers."""

    SPOT_PRICE_WEATHER = "spot_price_weather"
    TIME_OF_USE = "time_of_use"
    SELF_USE_ONLY = "self_use_only"
    MANUAL = "manual"


class SystemStatus(StrEnum):
    """System status values."""

    CHARGING = "charging"
    DISCHARGING = "discharging"
    SELF_USE = "self_use"
    HOUSE_FROM_GRID = "house_from_grid"
    IDLE = "idle"
    ERROR = "error"


# Strategy display names
STRATEGY_DISPLAY_NAMES: Final[dict[str, str]] = {
    StrategyKey.SPOT_PRICE_WEATHER: "Spot price + weather",
    StrategyKey.TIME_OF_USE: "Time of use",
    StrategyKey.SELF_USE_ONLY: "Self use only",
    StrategyKey.MANUAL: "Manual",
}

# Solax remote control mode values
SOLAX_MODE_GRID_CONTROL: Final = "Enabled Grid Control"
SOLAX_MODE_BATTERY_CONTROL: Final = "Enabled Battery Control"
SOLAX_MODE_SELF_USE: Final = "Enabled Self Use"
SOLAX_MODE_NO_DISCHARGE: Final = "Enabled No Discharge"
SOLAX_MODE_FEEDIN_PRIORITY: Final = "Enabled Feedin Priority"
SOLAX_MODE_DISABLED: Final = "Disabled"
