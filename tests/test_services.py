"""Tests for Solar Mind services (away periods, high-demand appliances)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ImportError:
    MockConfigEntry = None

from homeassistant.core import HomeAssistant

from custom_components.solar_mind.const import (
    CONF_PRICE_SENSOR,
    CONF_PRICE_SOURCE,
    CONF_REMOTECONTROL_ACTIVE_POWER,
    CONF_REMOTECONTROL_POWER_CONTROL,
    CONF_REMOTECONTROL_TRIGGER,
    CONF_SOLAX_DEVICE_TYPE,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    PriceSource,
    SolaxDeviceType,
)
from custom_components.solar_mind.coordinator import SolarMindCoordinator
from custom_components.solar_mind.models import SolarMindData

pytestmark = [
    pytest.mark.skipif(
        MockConfigEntry is None,
        reason="pytest-homeassistant-custom-component not installed",
    ),
    pytest.mark.asyncio,
]


def _solar_mind_config_entry():
    """Create a minimal MockConfigEntry for Solar Mind."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_solar_mind_services",
        title="Solar Mind",
        data={
            "name": "Solar Mind",
            CONF_SOLAX_DEVICE_TYPE: SolaxDeviceType.MODBUS_REMOTE,
            CONF_REMOTECONTROL_POWER_CONTROL: "select.foo",
            CONF_REMOTECONTROL_ACTIVE_POWER: "number.foo",
            CONF_REMOTECONTROL_TRIGGER: "button.foo",
            "battery_soc": "sensor.foo",
            CONF_PRICE_SENSOR: "sensor.foo",
            CONF_PRICE_SOURCE: PriceSource.CZECH_OTE,
        },
        options={CONF_UPDATE_INTERVAL: 5},
    )


async def test_add_away_period_service(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """add_away_period service adds period and persists."""
    entry = _solar_mind_config_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.solar_mind.coordinator.create_price_adapter",
            return_value=object(),
        ),
        patch.object(
            SolarMindCoordinator,
            "_load_persisted_data",
        ),
        patch.object(
            SolarMindCoordinator,
            "_save_persisted_data",
            new_callable=AsyncMock,
        ),
        patch.object(
            SolarMindCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value=SolarMindData(),
        ),
    ):
        coordinator = SolarMindCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    from custom_components.solar_mind import async_setup_services as setup_services

    await setup_services(hass)

    start = "2025-02-10T08:00:00+00:00"
    end = "2025-02-12T18:00:00+00:00"
    await hass.services.async_call(
        DOMAIN,
        "add_away_period",
        {
            "start": start,
            "end": end,
            "label": "Vacation",
            "reduce_load_percent": 70.0,
        },
        blocking=True,
    )

    assert len(coordinator._user_preferences.away_periods) == 1
    period = coordinator._user_preferences.away_periods[0]
    assert period.label == "Vacation"
    assert period.reduce_load_percent == 70.0
    assert period.start.isoformat().startswith("2025-02-10")
    assert period.end.isoformat().startswith("2025-02-12")


async def test_remove_away_period_service(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """remove_away_period service removes period by ID."""
    entry = _solar_mind_config_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.solar_mind.coordinator.create_price_adapter",
            return_value=object(),
        ),
        patch.object(SolarMindCoordinator, "_load_persisted_data"),
        patch.object(
            SolarMindCoordinator,
            "_save_persisted_data",
            new_callable=AsyncMock,
        ),
        patch.object(
            SolarMindCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value=SolarMindData(),
        ),
    ):
        coordinator = SolarMindCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    from custom_components.solar_mind import async_setup_services as setup_services

    await setup_services(hass)

    await hass.services.async_call(
        DOMAIN,
        "add_away_period",
        {
            "start": "2025-02-10T08:00:00+00:00",
            "end": "2025-02-12T18:00:00+00:00",
            "label": "Trip",
        },
        blocking=True,
    )
    period_id = coordinator._user_preferences.away_periods[0].id
    assert len(coordinator._user_preferences.away_periods) == 1

    await hass.services.async_call(
        DOMAIN,
        "remove_away_period",
        {"period_id": period_id},
        blocking=True,
    )
    assert len(coordinator._user_preferences.away_periods) == 0

    initial_count = len(coordinator._user_preferences.away_periods)
    await hass.services.async_call(
        DOMAIN,
        "remove_away_period",
        {"period_id": "nonexistent"},
        blocking=True,
    )
    assert len(coordinator._user_preferences.away_periods) == initial_count


async def test_set_high_demand_appliance_service(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """set_high_demand_appliance service adds/updates appliance."""
    entry = _solar_mind_config_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.solar_mind.coordinator.create_price_adapter",
            return_value=object(),
        ),
        patch.object(SolarMindCoordinator, "_load_persisted_data"),
        patch.object(
            SolarMindCoordinator,
            "_save_persisted_data",
            new_callable=AsyncMock,
        ),
        patch.object(
            SolarMindCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value=SolarMindData(),
        ),
    ):
        coordinator = SolarMindCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    from custom_components.solar_mind import async_setup_services as setup_services

    await setup_services(hass)

    await hass.services.async_call(
        DOMAIN,
        "set_high_demand_appliance",
        {"name": "Water heater", "power_w": 2000},
        blocking=True,
    )
    assert coordinator._user_preferences.high_demand_appliances["Water heater"] == 2000

    await hass.services.async_call(
        DOMAIN,
        "set_high_demand_appliance",
        {"name": "Water heater", "power_w": 2500},
        blocking=True,
    )
    assert coordinator._user_preferences.high_demand_appliances["Water heater"] == 2500


async def test_remove_high_demand_appliance_service(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """remove_high_demand_appliance service removes appliance."""
    entry = _solar_mind_config_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.solar_mind.coordinator.create_price_adapter",
            return_value=object(),
        ),
        patch.object(SolarMindCoordinator, "_load_persisted_data"),
        patch.object(
            SolarMindCoordinator,
            "_save_persisted_data",
            new_callable=AsyncMock,
        ),
        patch.object(
            SolarMindCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value=SolarMindData(),
        ),
    ):
        coordinator = SolarMindCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

    coordinator._user_preferences.high_demand_appliances["Water heater"] = 2000
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    from custom_components.solar_mind import async_setup_services as setup_services

    await setup_services(hass)

    await hass.services.async_call(
        DOMAIN,
        "remove_high_demand_appliance",
        {"name": "Water heater"},
        blocking=True,
    )
    assert "Water heater" not in coordinator._user_preferences.high_demand_appliances

    await hass.services.async_call(
        DOMAIN,
        "remove_high_demand_appliance",
        {"name": "Nonexistent"},
        blocking=True,
    )
    assert "Nonexistent" not in coordinator._user_preferences.high_demand_appliances
