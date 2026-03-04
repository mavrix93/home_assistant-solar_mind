"""Config flow for Solar Mind integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from custom_components.solar_mind.ha.const import (
    CONF_BATTERY_SOC,
    CONF_FIXED_HIGH_PRICE,
    CONF_FIXED_LOW_PRICE,
    CONF_MAX_PV_POWER,
    CONF_PRICE_MODE,
    CONF_PRICE_SENSOR,
    CONF_PV_AZIMUTH,
    CONF_PV_TILT,
    CONF_REMOTECONTROL_ACTIVE_POWER,
    CONF_REMOTECONTROL_AUTOREPEAT_DURATION,
    CONF_REMOTECONTROL_POWER_CONTROL,
    CONF_REMOTECONTROL_TRIGGER,
    DOMAIN,
    PriceMode,
)


_LOGGER = logging.getLogger(__name__)


def get_pv_system_schema() -> vol.Schema:
    """Get schema for PV system configuration."""
    return vol.Schema(
        {
            vol.Required(CONF_PV_AZIMUTH, default=180): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-180, max=180, step=1, unit_of_measurement="°", mode="box"
                )
            ),
            vol.Required(CONF_PV_TILT, default=35): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=90, step=1, unit_of_measurement="°", mode="box"
                )
            ),
            vol.Required(CONF_MAX_PV_POWER, default=5000): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100000, step=100, unit_of_measurement="W", mode="box"
                )
            ),
        }
    )


def get_price_mode_schema() -> vol.Schema:
    """Get schema for pricing mode selection."""
    return vol.Schema(
        {
            vol.Required(CONF_PRICE_MODE, default=PriceMode.SPOT): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=PriceMode.SPOT, label="Spot prices (OTE)"),
                        selector.SelectOptionDict(value=PriceMode.FIXED, label="Fixed tariff (high/low)"),
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }
    )


def get_spot_price_schema() -> vol.Schema:
    """Get schema for spot price sensor configuration."""
    return vol.Schema(
        {
            vol.Required(CONF_PRICE_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        }
    )


def get_fixed_price_schema() -> vol.Schema:
    """Get schema for fixed tariff price configuration."""
    return vol.Schema(
        {
            vol.Required(CONF_FIXED_HIGH_PRICE, default=6.0): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=20.0, step=0.01, unit_of_measurement="CZK/kWh", mode="box"
                )
            ),
            vol.Required(CONF_FIXED_LOW_PRICE, default=2.5): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=20.0, step=0.01, unit_of_measurement="CZK/kWh", mode="box"
                )
            ),
        }
    )


def get_solax_schema() -> vol.Schema:
    """Get schema for Solax entity configuration based on device type."""
    base_schema = {
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
        """Handle the initial step."""
        self._data[CONF_NAME] = (user_input or {}).get(CONF_NAME, "Solar Mind")
        return await self.async_step_pv_system()

    async def async_step_pv_system(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle PV system configuration."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_price_mode()

        return self.async_show_form(
            step_id="pv_system",
            data_schema=get_pv_system_schema(),
        )

    async def async_step_price_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle pricing mode selection (spot vs fixed tariff)."""
        if user_input is not None:
            self._data.update(user_input)
            mode = user_input[CONF_PRICE_MODE]
            if mode == PriceMode.SPOT:
                return await self.async_step_price_spot()
            return await self.async_step_price_fixed()

        return self.async_show_form(
            step_id="price_mode",
            data_schema=get_price_mode_schema(),
        )

    async def async_step_price_spot(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle spot price sensor configuration."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_solax()

        return self.async_show_form(
            step_id="price_spot",
            data_schema=get_spot_price_schema(),
        )

    async def async_step_price_fixed(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle fixed tariff price configuration."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_solax()

        return self.async_show_form(
            step_id="price_fixed",
            data_schema=get_fixed_price_schema(),
        )

    async def async_step_solax(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Solax entity configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title=self._data.get(CONF_NAME, "Solar Mind"),
                data=self._data
            )

        return self.async_show_form(
            step_id="solax",
            data_schema=get_solax_schema(),
            errors=errors,
            description_placeholders={
                "device_type": "Modbus Remote Control"
            },
        )
