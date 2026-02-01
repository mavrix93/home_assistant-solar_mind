"""Number entities for Solax PV Simulator."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    NUMBER_ACTIVE_POWER,
    NUMBER_AUTOREPEAT_DURATION,
    NUMBER_PASSIVE_GRID_POWER,
)
from .simulator import SolaxSimulator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solax Simulator number entities."""
    simulator: SolaxSimulator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SolaxActivePowerNumber(simulator, entry),
        SolaxAutorepeatDurationNumber(simulator, entry),
        SolaxPassiveGridPowerNumber(simulator, entry),
    ]

    async_add_entities(entities)


class SolaxNumberBase(NumberEntity):
    """Base class for Solax Simulator number entities."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        simulator: SolaxSimulator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        """Initialize the number entity."""
        self._simulator = simulator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
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


class SolaxActivePowerNumber(SolaxNumberBase):
    """Number entity for Solax remote control active power."""

    _attr_native_min_value = -10000
    _attr_native_max_value = 10000
    _attr_native_step = 100
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, simulator: SolaxSimulator, entry: ConfigEntry) -> None:
        """Initialize the number entity."""
        super().__init__(
            simulator,
            entry,
            NUMBER_ACTIVE_POWER,
            "Remote Control Active Power",
        )
        # Update limits based on simulator config
        self._attr_native_min_value = -simulator.state.max_discharge_power
        self._attr_native_max_value = simulator.state.max_charge_power

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._simulator.state.active_power_setpoint

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self._simulator.set_active_power(value)


class SolaxAutorepeatDurationNumber(SolaxNumberBase):
    """Number entity for Solax remote control autorepeat duration."""

    _attr_native_min_value = 60
    _attr_native_max_value = 7200
    _attr_native_step = 60
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(self, simulator: SolaxSimulator, entry: ConfigEntry) -> None:
        """Initialize the number entity."""
        super().__init__(
            simulator,
            entry,
            NUMBER_AUTOREPEAT_DURATION,
            "Remote Control Autorepeat Duration",
        )

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._simulator.state.autorepeat_duration

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self._simulator.set_autorepeat_duration(int(value))


class SolaxPassiveGridPowerNumber(SolaxNumberBase):
    """Number entity for Solax passive mode desired grid power."""

    _attr_native_min_value = -10000
    _attr_native_max_value = 10000
    _attr_native_step = 100
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, simulator: SolaxSimulator, entry: ConfigEntry) -> None:
        """Initialize the number entity."""
        super().__init__(
            simulator,
            entry,
            NUMBER_PASSIVE_GRID_POWER,
            "Passive Desired Grid Power",
        )
        # Update limits based on simulator config
        self._attr_native_min_value = -simulator.state.max_discharge_power
        self._attr_native_max_value = simulator.state.max_charge_power

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self._simulator.state.passive_grid_power

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self._simulator.set_passive_grid_power(value)
