"""Tests for Solar Mind config flow (require pytest-homeassistant-custom-component)."""
from __future__ import annotations

import pytest
from unittest.mock import patch

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ImportError:
    MockConfigEntry = None  # type: ignore[misc, assignment]

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from custom_components.solar_mind.const import (
    CONF_AUTOREPEAT_DURATION,
    CONF_CHARGE_PRICE_THRESHOLD,
    CONF_CHARGE_WINDOW_END,
    CONF_CHARGE_WINDOW_START,
    CONF_DISCHARGE_ALLOWED,
    CONF_DISCHARGE_PRICE_THRESHOLD,
    CONF_FALLBACK_STRATEGY,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PRICE_SENSOR,
    CONF_PRICE_SOURCE,
    CONF_REMOTECONTROL_ACTIVE_POWER,
    CONF_REMOTECONTROL_POWER_CONTROL,
    CONF_REMOTECONTROL_TRIGGER,
    CONF_SOLAX_DEVICE_TYPE,
    CONF_STRATEGY_SELECTOR_ENTITY,
    CONF_UPDATE_INTERVAL,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    PriceSource,
    StrategyKey,
    SolaxDeviceType,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

# Default options for options flow submit
DEFAULT_OPTIONS = {
    CONF_STRATEGY_SELECTOR_ENTITY: "",
    CONF_FALLBACK_STRATEGY: StrategyKey.SPOT_PRICE_WEATHER,
    CONF_CHARGE_PRICE_THRESHOLD: 0.05,
    CONF_DISCHARGE_PRICE_THRESHOLD: 0.15,
    CONF_MIN_SOC: 10,
    CONF_MAX_SOC: 95,
    CONF_MAX_CHARGE_POWER: 3000,
    CONF_MAX_DISCHARGE_POWER: 3000,
    CONF_CHARGE_WINDOW_START: 22,
    CONF_CHARGE_WINDOW_END: 6,
    CONF_DISCHARGE_ALLOWED: False,
    CONF_UPDATE_INTERVAL: 5,
    CONF_AUTOREPEAT_DURATION: 3600,
}


pytestmark = [
    pytest.mark.skipif(
        MockConfigEntry is None,
        reason="pytest-homeassistant-custom-component not installed",
    ),
    pytest.mark.asyncio,
]


async def test_user_step_show_form(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """Test initial step shows user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert CONF_NAME in result["data_schema"].schema
    assert CONF_SOLAX_DEVICE_TYPE in result["data_schema"].schema


async def test_full_flow_creates_entry(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """Test full config flow creates entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Solar Mind Test",
            CONF_SOLAX_DEVICE_TYPE: SolaxDeviceType.MODBUS_REMOTE,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "solax"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_REMOTECONTROL_POWER_CONTROL: "select.solax_remotecontrol_power_control",
            CONF_REMOTECONTROL_ACTIVE_POWER: "number.solax_remotecontrol_active_power",
            CONF_REMOTECONTROL_TRIGGER: "button.solax_remotecontrol_trigger",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "price"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PRICE_SENSOR: "sensor.nordpool_kwh",
            CONF_PRICE_SOURCE: PriceSource.NORD_POOL,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "weather"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_WEATHER_ENTITY: "weather.home"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "strategy"

    with patch(
        "custom_components.solar_mind.config_flow.SolarMindConfigFlow.async_set_unique_id"
    ), patch(
        "custom_components.solar_mind.config_flow.SolarMindConfigFlow._abort_if_unique_id_configured"
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_STRATEGY_SELECTOR_ENTITY: "",
                CONF_FALLBACK_STRATEGY: StrategyKey.SPOT_PRICE_WEATHER,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Solar Mind Test"
    assert result["data"][CONF_NAME] == "Solar Mind Test"
    assert result["data"][CONF_SOLAX_DEVICE_TYPE] == SolaxDeviceType.MODBUS_REMOTE
    assert result["data"][CONF_PRICE_SENSOR] == "sensor.nordpool_kwh"
    assert result["data"][CONF_PRICE_SOURCE] == PriceSource.NORD_POOL
    assert result["data"][CONF_WEATHER_ENTITY] == "weather.home"
    assert CONF_FALLBACK_STRATEGY in result["options"]


async def test_options_flow(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """Test options flow can be opened and saves options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Solar Mind",
        data={
            CONF_NAME: "Solar Mind",
            CONF_SOLAX_DEVICE_TYPE: SolaxDeviceType.MODBUS_REMOTE,
            CONF_PRICE_SENSOR: "sensor.price",
            CONF_PRICE_SOURCE: PriceSource.CZECH_OTE,
            CONF_REMOTECONTROL_POWER_CONTROL: "select.solax_power",
            CONF_REMOTECONTROL_ACTIVE_POWER: "number.solax_power",
            CONF_REMOTECONTROL_TRIGGER: "button.solax_trigger",
        },
        options=DEFAULT_OPTIONS.copy(),
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    options_input = {**DEFAULT_OPTIONS}
    options_input[CONF_STRATEGY_SELECTOR_ENTITY] = "input_select.solar_mind_strategy"
    options_input[CONF_FALLBACK_STRATEGY] = StrategyKey.SELF_USE_ONLY

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        options_input,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_FALLBACK_STRATEGY] == StrategyKey.SELF_USE_ONLY
    assert entry.options[CONF_STRATEGY_SELECTOR_ENTITY] == "input_select.solar_mind_strategy"
