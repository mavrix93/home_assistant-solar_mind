"""Config flow for Solax PV Simulator integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_CAPACITY,
    CONF_INITIAL_SOC,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_PV_POWER,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_INITIAL_SOC,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_PV_POWER,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SolaxSimulatorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solax PV Simulator."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Create unique ID based on name
            await self.async_set_unique_id(
                f"solax_simulator_{user_input.get(CONF_NAME, 'default').lower().replace(' ', '_')}"
            )
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input.get(CONF_NAME, "Solax Simulator"),
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME, default="Solax Simulator"
                    ): str,
                    vol.Required(
                        CONF_BATTERY_CAPACITY, default=DEFAULT_BATTERY_CAPACITY
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1000,
                            max=50000,
                            step=500,
                            unit_of_measurement="Wh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_MAX_PV_POWER, default=DEFAULT_MAX_PV_POWER
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1000,
                            max=30000,
                            step=500,
                            unit_of_measurement="W",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_MAX_CHARGE_POWER, default=DEFAULT_MAX_CHARGE_POWER
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1000,
                            max=15000,
                            step=500,
                            unit_of_measurement="W",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_MAX_DISCHARGE_POWER, default=DEFAULT_MAX_DISCHARGE_POWER
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1000,
                            max=15000,
                            step=500,
                            unit_of_measurement="W",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_INITIAL_SOC, default=DEFAULT_INITIAL_SOC
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100,
                            step=5,
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
            errors=errors,
        )
