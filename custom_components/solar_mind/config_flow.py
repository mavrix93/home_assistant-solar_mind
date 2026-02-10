"""Config flow for Solar Mind integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from custom_components.solar_mind.ha.const import CONF_BATTERY_SOC, CONF_ENERGY_STORAGE_MODE, CONF_REMOTECONTROL_ACTIVE_POWER, CONF_REMOTECONTROL_AUTOREPEAT_DURATION, CONF_REMOTECONTROL_POWER_CONTROL, CONF_REMOTECONTROL_TRIGGER, DOMAIN


_LOGGER = logging.getLogger(__name__)


def get_solax_schema() -> vol.Schema:
    """Get schema for Solax entity configuration based on device type."""
    base_schema = {
        vol.Optional(CONF_ENERGY_STORAGE_MODE): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="select")
        ),
        vol.Optional(CONF_BATTERY_SOC): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
                vol.Required(CONF_REMOTECONTROL_POWER_CONTROL): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="select")
                ),
                vol.Required(CONF_REMOTECONTROL_ACTIVE_POWER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
                vol.Required(CONF_REMOTECONTROL_TRIGGER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="button")
                ),
                vol.Optional(
                    CONF_REMOTECONTROL_AUTOREPEAT_DURATION
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
            }
        
   
    return vol.Schema(base_schema)


class SolarMindConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Mind."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:

        self._data[CONF_NAME] = user_input.get(CONF_NAME, "Solar Mind")
        return await self.async_step_solax()


    async def async_step_solax(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Solax entity configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self._abort_if_unique_id_configured()

        return self.async_show_form(
            step_id="solax",
            data_schema=get_solax_schema(self._device_type),
            errors=errors,
            description_placeholders={
                "device_type": "Modbus Remote Control"
                if self._device_type == SolaxDeviceType.MODBUS_REMOTE
                else "Passive Mode (Sofar)"
            },
        )
