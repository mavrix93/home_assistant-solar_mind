"""Tests for Solar Mind config flow (require pytest-homeassistant-custom-component)."""
import pytest
from unittest.mock import patch

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ImportError:
    MockConfigEntry = None  # type: ignore[misc, assignment]

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

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
    CONF_REMOTECONTROL_POWER_CONTROL,
    CONF_REMOTECONTROL_TRIGGER,
    DOMAIN,
    PriceMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


pytestmark = [
    pytest.mark.skipif(
        MockConfigEntry is None,
        reason="pytest-homeassistant-custom-component not installed",
    ),
    pytest.mark.asyncio,
]


async def test_user_step_goes_to_pv_system(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """Test initial step proceeds to PV system configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # User step immediately goes to pv_system step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pv_system"


async def test_full_flow_spot_price_creates_entry(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """Test full config flow with spot price creates entry."""
    # Step 1: User step (auto-proceeds to pv_system)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pv_system"

    # Step 2: PV system configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PV_AZIMUTH: 180,
            CONF_PV_TILT: 35,
            CONF_MAX_PV_POWER: 5000,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "price_mode"

    # Step 3: Price mode selection (spot)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PRICE_MODE: PriceMode.SPOT,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "price_spot"

    # Step 4: Spot price sensor selection
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PRICE_SENSOR: "sensor.spot_price",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "solax"

    # Step 5: Solax entity configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_REMOTECONTROL_POWER_CONTROL: "select.solax_remotecontrol_power_control",
            CONF_REMOTECONTROL_ACTIVE_POWER: "number.solax_remotecontrol_active_power",
            CONF_REMOTECONTROL_TRIGGER: "button.solax_remotecontrol_trigger",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Solar Mind"
    assert result["data"][CONF_PV_AZIMUTH] == 180
    assert result["data"][CONF_PV_TILT] == 35
    assert result["data"][CONF_MAX_PV_POWER] == 5000
    assert result["data"][CONF_PRICE_MODE] == PriceMode.SPOT
    assert result["data"][CONF_PRICE_SENSOR] == "sensor.spot_price"


async def test_full_flow_fixed_price_creates_entry(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """Test full config flow with fixed tariff creates entry."""
    # Step 1: User step
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pv_system"

    # Step 2: PV system configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PV_AZIMUTH: 180,
            CONF_PV_TILT: 35,
            CONF_MAX_PV_POWER: 5000,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "price_mode"

    # Step 3: Price mode selection (fixed)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PRICE_MODE: PriceMode.FIXED,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "price_fixed"

    # Step 4: Fixed price configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_FIXED_HIGH_PRICE: 6.0,
            CONF_FIXED_LOW_PRICE: 2.5,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "solax"

    # Step 5: Solax entity configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_REMOTECONTROL_POWER_CONTROL: "select.solax_power",
            CONF_REMOTECONTROL_ACTIVE_POWER: "number.solax_power",
            CONF_REMOTECONTROL_TRIGGER: "button.solax_trigger",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Solar Mind"
    assert result["data"][CONF_PRICE_MODE] == PriceMode.FIXED
    assert result["data"][CONF_FIXED_HIGH_PRICE] == 6.0
    assert result["data"][CONF_FIXED_LOW_PRICE] == 2.5
