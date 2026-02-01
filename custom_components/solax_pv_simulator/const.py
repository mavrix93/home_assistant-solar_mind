"""Constants for the Solax PV Simulator integration."""
from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "solax_pv_simulator"

# Configuration keys
CONF_BATTERY_CAPACITY: Final = "battery_capacity"
CONF_MAX_CHARGE_POWER: Final = "max_charge_power"
CONF_MAX_DISCHARGE_POWER: Final = "max_discharge_power"
CONF_MAX_PV_POWER: Final = "max_pv_power"
CONF_INITIAL_SOC: Final = "initial_soc"
CONF_SIMULATION_SPEED: Final = "simulation_speed"

# Default values
DEFAULT_BATTERY_CAPACITY: Final = 10000  # Wh (10 kWh)
DEFAULT_MAX_CHARGE_POWER: Final = 5000  # W
DEFAULT_MAX_DISCHARGE_POWER: Final = 5000  # W
DEFAULT_MAX_PV_POWER: Final = 10000  # W (10 kW peak)
DEFAULT_INITIAL_SOC: Final = 50  # %
DEFAULT_SIMULATION_SPEED: Final = 1.0  # Real-time

# Solax Remote Control Mode options (matching real Solax Modbus)
class RemoteControlMode(StrEnum):
    """Remote control power control modes."""
    
    DISABLED = "Disabled"
    GRID_CONTROL = "Enabled Grid Control"
    BATTERY_CONTROL = "Enabled Battery Control"
    SELF_USE = "Enabled Self Use"
    NO_DISCHARGE = "Enabled No Discharge"
    FEEDIN_PRIORITY = "Enabled Feedin Priority"


# Energy Storage Mode options
class EnergyStorageMode(StrEnum):
    """Energy storage mode options."""
    
    SELF_USE = "Self Use"
    FEED_IN_PRIORITY = "Feed In Priority"
    BACKUP = "Backup"
    MANUAL = "Manual"


# Sensor types
SENSOR_BATTERY_SOC: Final = "battery_soc"
SENSOR_BATTERY_POWER: Final = "battery_power"
SENSOR_PV_POWER: Final = "pv_power"
SENSOR_GRID_POWER: Final = "grid_power"
SENSOR_HOUSE_LOAD: Final = "house_load"
SENSOR_INVERTER_TEMPERATURE: Final = "inverter_temperature"
SENSOR_BATTERY_TEMPERATURE: Final = "battery_temperature"
SENSOR_PV_VOLTAGE: Final = "pv_voltage"
SENSOR_PV_CURRENT: Final = "pv_current"
SENSOR_GRID_VOLTAGE: Final = "grid_voltage"
SENSOR_GRID_FREQUENCY: Final = "grid_frequency"
SENSOR_ENERGY_TODAY: Final = "energy_today"
SENSOR_ENERGY_TOTAL: Final = "energy_total"

# Number entity types
NUMBER_ACTIVE_POWER: Final = "remotecontrol_active_power"
NUMBER_AUTOREPEAT_DURATION: Final = "remotecontrol_autorepeat_duration"
NUMBER_PASSIVE_GRID_POWER: Final = "passive_desired_grid_power"

# Select entity types
SELECT_POWER_CONTROL: Final = "remotecontrol_power_control"
SELECT_ENERGY_STORAGE_MODE: Final = "energy_storage_mode"

# Button entity types
BUTTON_TRIGGER: Final = "remotecontrol_trigger"
BUTTON_PASSIVE_UPDATE: Final = "passive_update_battery_charge_discharge"

# Weather conditions for simulation
class SimulatedWeather(StrEnum):
    """Simulated weather conditions affecting PV production."""
    
    SUNNY = "sunny"
    PARTLY_CLOUDY = "partlycloudy"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    NIGHT = "night"


# Weather to PV production multipliers
WEATHER_PV_MULTIPLIER: Final[dict[str, float]] = {
    SimulatedWeather.SUNNY: 1.0,
    SimulatedWeather.PARTLY_CLOUDY: 0.6,
    SimulatedWeather.CLOUDY: 0.2,
    SimulatedWeather.RAINY: 0.1,
    SimulatedWeather.NIGHT: 0.0,
}
