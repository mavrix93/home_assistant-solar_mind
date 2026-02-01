"""Button entities for Solax PV Simulator."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BUTTON_PASSIVE_UPDATE,
    BUTTON_TRIGGER,
    DOMAIN,
)
from .simulator import SolaxSimulator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solax Simulator button entities."""
    simulator: SolaxSimulator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SolaxRemoteControlTriggerButton(simulator, entry),
        SolaxPassiveUpdateButton(simulator, entry),
    ]

    async_add_entities(entities)


class SolaxButtonBase(ButtonEntity):
    """Base class for Solax Simulator button entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        simulator: SolaxSimulator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        """Initialize the button entity."""
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


class SolaxRemoteControlTriggerButton(SolaxButtonBase):
    """Button entity for Solax remote control trigger."""

    def __init__(self, simulator: SolaxSimulator, entry: ConfigEntry) -> None:
        """Initialize the button entity."""
        super().__init__(
            simulator,
            entry,
            BUTTON_TRIGGER,
            "Remote Control Trigger",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        self._simulator.trigger_remote_control()


class SolaxPassiveUpdateButton(SolaxButtonBase):
    """Button entity for Solax passive mode update."""

    def __init__(self, simulator: SolaxSimulator, entry: ConfigEntry) -> None:
        """Initialize the button entity."""
        super().__init__(
            simulator,
            entry,
            BUTTON_PASSIVE_UPDATE,
            "Passive Update Battery",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        self._simulator.trigger_passive_update()
