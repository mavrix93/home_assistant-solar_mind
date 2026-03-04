"""Select entities for Solax PV Simulator."""

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    EnergyStorageMode,
    RemoteControlMode,
    SELECT_ENERGY_STORAGE_MODE,
    SELECT_POWER_CONTROL,
)
from .simulator import SolaxSimulator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solax Simulator select entities."""
    simulator: SolaxSimulator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SolaxRemoteControlModeSelect(simulator, entry),
        SolaxEnergyStorageModeSelect(simulator, entry),
    ]

    async_add_entities(entities)


class SolaxSelectBase(SelectEntity):
    """Base class for Solax Simulator select entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        simulator: SolaxSimulator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        """Initialize the select entity."""
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


class SolaxRemoteControlModeSelect(SolaxSelectBase):
    """Select entity for Solax remote control power control mode."""

    _attr_options = [mode.value for mode in RemoteControlMode]

    def __init__(self, simulator: SolaxSimulator, entry: ConfigEntry) -> None:
        """Initialize the select entity."""
        super().__init__(
            simulator,
            entry,
            SELECT_POWER_CONTROL,
            "Remote Control Power Control",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self._simulator.state.remote_control_mode.value

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self._simulator.set_remote_control_mode(option)


class SolaxEnergyStorageModeSelect(SolaxSelectBase):
    """Select entity for Solax energy storage mode."""

    _attr_options = [mode.value for mode in EnergyStorageMode]

    def __init__(self, simulator: SolaxSimulator, entry: ConfigEntry) -> None:
        """Initialize the select entity."""
        super().__init__(
            simulator,
            entry,
            SELECT_ENERGY_STORAGE_MODE,
            "Energy Storage Mode",
        )

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self._simulator.state.energy_storage_mode.value

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self._simulator.set_energy_storage_mode(option)
