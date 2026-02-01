"""The Solax PV Simulator integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .simulator import SolaxSimulator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solax PV Simulator from a config entry."""
    _LOGGER.info("Setting up Solax PV Simulator: %s", entry.title)
    
    # Create simulator instance
    simulator = SolaxSimulator(hass, entry)
    
    # Store in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = simulator
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Start the simulator
    await simulator.async_start()
    
    # Register services
    await async_setup_services(hass)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Solax PV Simulator: %s", entry.title)
    
    # Stop the simulator
    simulator: SolaxSimulator = hass.data[DOMAIN][entry.entry_id]
    await simulator.async_stop()
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the Solax PV Simulator."""
    from .services import async_register_services
    await async_register_services(hass)
