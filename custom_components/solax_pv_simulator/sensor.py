"""Sensor entities for Solax PV Simulator."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SENSOR_BATTERY_POWER,
    SENSOR_BATTERY_SOC,
    SENSOR_BATTERY_TEMPERATURE,
    SENSOR_ENERGY_TODAY,
    SENSOR_ENERGY_TOTAL,
    SENSOR_GRID_FREQUENCY,
    SENSOR_GRID_POWER,
    SENSOR_GRID_VOLTAGE,
    SENSOR_HOUSE_LOAD,
    SENSOR_INVERTER_TEMPERATURE,
    SENSOR_PV_CURRENT,
    SENSOR_PV_POWER,
    SENSOR_PV_VOLTAGE,
)
from .simulator import SimulatorState, SolaxSimulator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SolaxSensorEntityDescription(SensorEntityDescription):
    """Describes a Solax Simulator sensor entity."""

    value_fn: Callable[[SimulatorState], Any] | None = None


SENSOR_DESCRIPTIONS: tuple[SolaxSensorEntityDescription, ...] = (
    SolaxSensorEntityDescription(
        key=SENSOR_BATTERY_SOC,
        name="Battery SOC",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.battery_soc, 1),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_BATTERY_POWER,
        name="Battery Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.battery_power, 0),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_BATTERY_TEMPERATURE,
        name="Battery Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.battery_temperature, 1),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_PV_POWER,
        name="PV Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.pv_power, 0),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_PV_VOLTAGE,
        name="PV Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.pv_voltage, 1),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_PV_CURRENT,
        name="PV Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.pv_current, 2),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_GRID_POWER,
        name="Grid Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.grid_power, 0),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_GRID_VOLTAGE,
        name="Grid Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.grid_voltage, 1),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_GRID_FREQUENCY,
        name="Grid Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.grid_frequency, 2),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_HOUSE_LOAD,
        name="House Load",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.house_load, 0),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_INVERTER_TEMPERATURE,
        name="Inverter Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: round(state.inverter_temperature, 1),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_ENERGY_TODAY,
        name="Energy Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda state: round(state.energy_today, 2),
    ),
    SolaxSensorEntityDescription(
        key=SENSOR_ENERGY_TOTAL,
        name="Energy Total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda state: round(state.energy_total, 2),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solax Simulator sensor entities."""
    simulator: SolaxSimulator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SolaxSensor(simulator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


class SolaxSensor(SensorEntity):
    """Sensor entity for Solax Simulator."""

    _attr_has_entity_name = True
    entity_description: SolaxSensorEntityDescription

    def __init__(
        self,
        simulator: SolaxSimulator,
        entry: ConfigEntry,
        description: SolaxSensorEntityDescription,
    ) -> None:
        """Initialize the sensor entity."""
        self._simulator = simulator
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Solax (Simulated)",
            model="PV Simulator",
            sw_version="1.0.0",
        )
        self._remove_listener: callable | None = None

    async def async_added_to_hass(self) -> None:
        """Register state listener."""
        self._remove_listener = self._simulator.add_listener(
            self._handle_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Remove state listener."""
        if self._remove_listener:
            self._remove_listener()

    @callback
    def _handle_state_update(self) -> None:
        """Handle state update from simulator."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self._simulator.state)
        return None
