"""Solar Mind integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from custom_components.solar_mind.ha.const import DOMAIN
from custom_components.solar_mind.ha.coordinator import SolarMindCoordinator

_LOGGER: logging.Logger = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [Platform.SENSOR, Platform.BUTTON, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Mind from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = SolarMindCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Options updated for Solar Mind: %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
    

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up Solar Mind services."""
    from .ha.services import async_setup_services as setup_services

    await setup_services(hass)
