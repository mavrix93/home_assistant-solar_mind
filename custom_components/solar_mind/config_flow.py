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

from .const import (
    CONF_BATTERY_SOC,
    CONF_CHARGE_PRICE_THRESHOLD,
    CONF_CHARGE_WINDOW_END,
    CONF_CHARGE_WINDOW_START,
    CONF_DISCHARGE_ALLOWED,
    CONF_DISCHARGE_PRICE_THRESHOLD,
    CONF_ENERGY_STORAGE_MODE,
    CONF_FALLBACK_STRATEGY,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PASSIVE_DESIRED_GRID_POWER,
    CONF_PASSIVE_UPDATE_TRIGGER,
    CONF_PRICE_SENSOR,
    CONF_PRICE_SOURCE,
    CONF_REMOTECONTROL_ACTIVE_POWER,
    CONF_REMOTECONTROL_AUTOREPEAT_DURATION,
    CONF_REMOTECONTROL_POWER_CONTROL,
    CONF_REMOTECONTROL_TRIGGER,
    CONF_SOLAX_DEVICE_TYPE,
    CONF_STRATEGY_SELECTOR_ENTITY,
    CONF_UPDATE_INTERVAL,
    CONF_WEATHER_ENTITY,
    CONF_AUTOREPEAT_DURATION,
    DEFAULT_CHARGE_PRICE_THRESHOLD,
    DEFAULT_CHARGE_WINDOW_END,
    DEFAULT_CHARGE_WINDOW_START,
    DEFAULT_DISCHARGE_ALLOWED,
    DEFAULT_DISCHARGE_PRICE_THRESHOLD,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_AUTOREPEAT_DURATION,
    DOMAIN,
    PriceSource,
    SolaxDeviceType,
    StrategyKey,
    STRATEGY_DISPLAY_NAMES,
)

_LOGGER = logging.getLogger(__name__)


def get_solax_schema(device_type: SolaxDeviceType) -> vol.Schema:
    """Get schema for Solax entity configuration based on device type."""
    base_schema = {
        vol.Optional(CONF_ENERGY_STORAGE_MODE): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="select")
        ),
        vol.Optional(CONF_BATTERY_SOC): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
    }

    if device_type == SolaxDeviceType.MODBUS_REMOTE:
        base_schema.update(
            {
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
        )
    else:  # PASSIVE_SOFAR
        base_schema.update(
            {
                vol.Required(CONF_PASSIVE_DESIRED_GRID_POWER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="number")
                ),
                vol.Required(CONF_PASSIVE_UPDATE_TRIGGER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="button")
                ),
            }
        )

    return vol.Schema(base_schema)


class SolarMindConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Mind."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._device_type: SolaxDeviceType = SolaxDeviceType.MODBUS_REMOTE

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - select device type."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data[CONF_NAME] = user_input.get(CONF_NAME, "Solar Mind")
            self._device_type = SolaxDeviceType(user_input[CONF_SOLAX_DEVICE_TYPE])
            self._data[CONF_SOLAX_DEVICE_TYPE] = self._device_type
            return await self.async_step_solax()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME, default="Solar Mind"): str,
                    vol.Required(
                        CONF_SOLAX_DEVICE_TYPE,
                        default=SolaxDeviceType.MODBUS_REMOTE,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=SolaxDeviceType.MODBUS_REMOTE,
                                    label="Modbus Remote Control (Gen4)",
                                ),
                                selector.SelectOptionDict(
                                    value=SolaxDeviceType.PASSIVE_SOFAR,
                                    label="Passive Mode (Sofar)",
                                ),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_solax(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Solax entity configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_price()

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

    async def async_step_price(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle price sensor configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_weather()

        return self.async_show_form(
            step_id="price",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRICE_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required(
                        CONF_PRICE_SOURCE, default=PriceSource.CZECH_OTE
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=PriceSource.CZECH_OTE,
                                    label="Czech OTE (cz_energy_spot_prices)",
                                ),
                                selector.SelectOptionDict(
                                    value=PriceSource.NORD_POOL,
                                    label="Nord Pool",
                                ),
                                selector.SelectOptionDict(
                                    value=PriceSource.GENERIC,
                                    label="Generic (manual configuration)",
                                ),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_weather(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle weather entity configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_strategy()

        return self.async_show_form(
            step_id="weather",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="weather")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_strategy(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle strategy selector configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            # Set unique ID based on name
            await self.async_set_unique_id(
                f"solar_mind_{self._data.get(CONF_NAME, 'default').lower().replace(' ', '_')}"
            )
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self._data.get(CONF_NAME, "Solar Mind"),
                data=self._data,
                options={
                    CONF_CHARGE_PRICE_THRESHOLD: DEFAULT_CHARGE_PRICE_THRESHOLD,
                    CONF_DISCHARGE_PRICE_THRESHOLD: DEFAULT_DISCHARGE_PRICE_THRESHOLD,
                    CONF_MIN_SOC: DEFAULT_MIN_SOC,
                    CONF_MAX_SOC: DEFAULT_MAX_SOC,
                    CONF_MAX_CHARGE_POWER: DEFAULT_MAX_CHARGE_POWER,
                    CONF_MAX_DISCHARGE_POWER: DEFAULT_MAX_DISCHARGE_POWER,
                    CONF_CHARGE_WINDOW_START: DEFAULT_CHARGE_WINDOW_START,
                    CONF_CHARGE_WINDOW_END: DEFAULT_CHARGE_WINDOW_END,
                    CONF_DISCHARGE_ALLOWED: DEFAULT_DISCHARGE_ALLOWED,
                    CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                    CONF_AUTOREPEAT_DURATION: DEFAULT_AUTOREPEAT_DURATION,
                    CONF_FALLBACK_STRATEGY: StrategyKey.SPOT_PRICE_WEATHER,
                },
            )

        return self.async_show_form(
            step_id="strategy",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_STRATEGY_SELECTOR_ENTITY, default=""): vol.Any(
                        vol.In([""]),
                        selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain=["input_select", "select"]
                            )
                        ),
                    ),
                    vol.Required(
                        CONF_FALLBACK_STRATEGY, default=StrategyKey.SPOT_PRICE_WEATHER
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=key, label=name)
                                for key, name in STRATEGY_DISPLAY_NAMES.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SolarMindOptionsFlowHandler:
        """Get the options flow for this handler."""
        return SolarMindOptionsFlowHandler(config_entry)


class SolarMindOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Solar Mind options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_STRATEGY_SELECTOR_ENTITY,
                        default=options.get(CONF_STRATEGY_SELECTOR_ENTITY, ""),
                    ): vol.Any(
                        vol.In([""]),
                        selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain=["input_select", "select"]
                            )
                        ),
                    ),
                    vol.Required(
                        CONF_FALLBACK_STRATEGY,
                        default=options.get(
                            CONF_FALLBACK_STRATEGY, StrategyKey.SPOT_PRICE_WEATHER
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=key, label=name)
                                for key, name in STRATEGY_DISPLAY_NAMES.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_CHARGE_PRICE_THRESHOLD,
                        default=options.get(
                            CONF_CHARGE_PRICE_THRESHOLD, DEFAULT_CHARGE_PRICE_THRESHOLD
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=10,
                            step=0.001,
                            unit_of_measurement="CZK/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_DISCHARGE_PRICE_THRESHOLD,
                        default=options.get(
                            CONF_DISCHARGE_PRICE_THRESHOLD,
                            DEFAULT_DISCHARGE_PRICE_THRESHOLD,
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=10,
                            step=0.001,
                            unit_of_measurement="CZK/kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_MIN_SOC,
                        default=options.get(CONF_MIN_SOC, DEFAULT_MIN_SOC),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100,
                            step=1,
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(
                        CONF_MAX_SOC,
                        default=options.get(CONF_MAX_SOC, DEFAULT_MAX_SOC),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100,
                            step=1,
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(
                        CONF_MAX_CHARGE_POWER,
                        default=options.get(
                            CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=15000,
                            step=100,
                            unit_of_measurement="W",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_MAX_DISCHARGE_POWER,
                        default=options.get(
                            CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=15000,
                            step=100,
                            unit_of_measurement="W",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_CHARGE_WINDOW_START,
                        default=options.get(
                            CONF_CHARGE_WINDOW_START, DEFAULT_CHARGE_WINDOW_START
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=23,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_CHARGE_WINDOW_END,
                        default=options.get(
                            CONF_CHARGE_WINDOW_END, DEFAULT_CHARGE_WINDOW_END
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=23,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_DISCHARGE_ALLOWED,
                        default=options.get(
                            CONF_DISCHARGE_ALLOWED, DEFAULT_DISCHARGE_ALLOWED
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=options.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=60,
                            step=1,
                            unit_of_measurement="min",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_AUTOREPEAT_DURATION,
                        default=options.get(
                            CONF_AUTOREPEAT_DURATION, DEFAULT_AUTOREPEAT_DURATION
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=60,
                            max=7200,
                            step=60,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            errors=errors,
        )
