"""Services for the Solar Mind integration."""

import logging
from datetime import datetime, timezone
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from custom_components.solar_mind.ha.const import DOMAIN
from custom_components.solar_mind.ha.coordinator import SolarMindCoordinator

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_CHARGE_FROM_GRID = "charge_battery_from_grid"
SERVICE_DISCHARGE_TO_GRID = "discharge_battery_to_grid"
SERVICE_SET_SELF_USE = "set_self_use"
SERVICE_SET_HOUSE_FROM_GRID = "set_house_use_grid"

SERVICE_SET_BATTERY_FOR_HOUSE = "set_battery_for_house"
SERVICE_APPLY_STRATEGY = "apply_strategy"
# Service schemas
SCHEMA_CHARGE = vol.Schema(
    {
        vol.Optional("power_w"): cv.positive_int,
        vol.Optional("duration_seconds"): cv.positive_int,
    }
)

SCHEMA_DISCHARGE = vol.Schema(
    {
        vol.Optional("power_w"): cv.positive_int,
        vol.Optional("duration_seconds"): cv.positive_int,
    }
)

SCHEMA_EMPTY = vol.Schema({})



async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up Solar Mind services."""
    
    async def _get_coordinator() -> SolarMindCoordinator | None:
        """Get the first available coordinator."""
        if DOMAIN not in hass.data:
            return None
        
        for entry_id, coordinator in hass.data[DOMAIN].items():
            if isinstance(coordinator, SolarMindCoordinator):
                return coordinator
        
        return None

    async def handle_charge_from_grid(call: ServiceCall) -> None:
        """Handle charge from grid service call."""
        coordinator = await _get_coordinator()
        if coordinator is None:
            _LOGGER.error("No Solar Mind coordinator found")
            return
        
        power_w = call.data.get("power_w")
        duration_seconds = call.data.get("duration_seconds")
        
        _LOGGER.info(
            "Service call: charge from grid (power=%s, duration=%s)",
            power_w,
            duration_seconds,
        )
        
        await coordinator.async_charge_from_grid(power_w, duration_seconds)

    async def handle_discharge_to_grid(call: ServiceCall) -> None:
        """Handle discharge to grid service call."""
        coordinator = await _get_coordinator()
        if coordinator is None:
            _LOGGER.error("No Solar Mind coordinator found")
            return
        
        power_w = call.data.get("power_w")
        duration_seconds = call.data.get("duration_seconds")
        
        _LOGGER.info(
            "Service call: discharge to grid (power=%s, duration=%s)",
            power_w,
            duration_seconds,
        )
        
        await coordinator.async_discharge_to_grid(power_w, duration_seconds)

    async def handle_set_self_use(call: ServiceCall) -> None:
        """Handle set self-use service call."""
        coordinator = await _get_coordinator()
        if coordinator is None:
            _LOGGER.error("No Solar Mind coordinator found")
            return
        
        _LOGGER.info("Service call: set self-use mode")
        await coordinator.async_set_self_use()

    async def handle_set_house_from_grid(call: ServiceCall) -> None:
        """Handle set house from grid service call."""
        coordinator = await _get_coordinator()
        if coordinator is None:
            _LOGGER.error("No Solar Mind coordinator found")
            return
        
        _LOGGER.info("Service call: set house from grid (no discharge)")
        await coordinator.async_set_house_from_grid()

    async def handle_set_battery_for_house(call: ServiceCall) -> None:
        """Handle set battery for house service call (alias for self-use)."""
        coordinator = await _get_coordinator()
        if coordinator is None:
            _LOGGER.error("No Solar Mind coordinator found")
            return
        
        _LOGGER.info("Service call: set battery for house")
        await coordinator.async_set_self_use()

    async def handle_apply_strategy(call: ServiceCall) -> None:
        """Handle apply strategy service call."""
        coordinator = await _get_coordinator()
        if coordinator is None:
            _LOGGER.error("No Solar Mind coordinator found")
            return
        
        _LOGGER.info("Service call: apply strategy")
        await coordinator.async_apply_strategy()




    # Register services (only if not already registered)
    if not hass.services.has_service(DOMAIN, SERVICE_CHARGE_FROM_GRID):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CHARGE_FROM_GRID,
            handle_charge_from_grid,
            schema=SCHEMA_CHARGE,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_DISCHARGE_TO_GRID):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DISCHARGE_TO_GRID,
            handle_discharge_to_grid,
            schema=SCHEMA_DISCHARGE,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_SELF_USE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_SELF_USE,
            handle_set_self_use,
            schema=SCHEMA_EMPTY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_HOUSE_FROM_GRID):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_HOUSE_FROM_GRID,
            handle_set_house_from_grid,
            schema=SCHEMA_EMPTY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_BATTERY_FOR_HOUSE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_BATTERY_FOR_HOUSE,
            handle_set_battery_for_house,
            schema=SCHEMA_EMPTY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_APPLY_STRATEGY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_APPLY_STRATEGY,
            handle_apply_strategy,
            schema=SCHEMA_EMPTY,
        )
