"""Tests for Solar Mind services."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ImportError:
    MockConfigEntry = None

from homeassistant.core import HomeAssistant

from custom_components.solar_mind.ha.const import (
    CONF_BATTERY_SOC,
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
from custom_components.solar_mind.ha.coordinator import SolarMindCoordinator
from custom_components.solar_mind.mind.models import SolarMindData

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
            CONF_PV_AZIMUTH: 180,
            CONF_PV_TILT: 35,
            CONF_MAX_PV_POWER: 5000,
            CONF_PRICE_MODE: PriceMode.SPOT,
            CONF_PRICE_SENSOR: "sensor.spot_price",
            CONF_REMOTECONTROL_POWER_CONTROL: "select.foo",
            CONF_REMOTECONTROL_ACTIVE_POWER: "number.foo",
            CONF_REMOTECONTROL_TRIGGER: "button.foo",
            CONF_BATTERY_SOC: "sensor.battery_soc",
        },
        options={},
    )


async def test_charge_from_grid_service(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """charge_battery_from_grid service triggers charging."""
    entry = _solar_mind_config_entry()
    entry.add_to_hass(hass)

    with (
        patch.object(
            SolarMindCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value=SolarMindData(),
        ),
        patch.object(
            SolarMindCoordinator,
            "async_charge_from_grid",
            new_callable=AsyncMock,
        ) as mock_charge,
    ):
        coordinator = SolarMindCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        from custom_components.solar_mind import async_setup_services as setup_services
        await setup_services(hass)

        await hass.services.async_call(
            DOMAIN,
            "charge_battery_from_grid",
            {"power_w": 3000, "duration_seconds": 1800},
            blocking=True,
        )

        mock_charge.assert_called_once_with(3000, 1800)


async def test_discharge_to_grid_service(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """discharge_battery_to_grid service triggers discharging."""
    entry = _solar_mind_config_entry()
    entry.add_to_hass(hass)

    with (
        patch.object(
            SolarMindCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value=SolarMindData(),
        ),
        patch.object(
            SolarMindCoordinator,
            "async_discharge_to_grid",
            new_callable=AsyncMock,
        ) as mock_discharge,
    ):
        coordinator = SolarMindCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        from custom_components.solar_mind import async_setup_services as setup_services
        await setup_services(hass)

        await hass.services.async_call(
            DOMAIN,
            "discharge_battery_to_grid",
            {"power_w": 2500},
            blocking=True,
        )

        mock_discharge.assert_called_once_with(2500, None)


async def test_set_self_use_service(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """set_self_use service sets self-use mode."""
    entry = _solar_mind_config_entry()
    entry.add_to_hass(hass)

    with (
        patch.object(
            SolarMindCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value=SolarMindData(),
        ),
        patch.object(
            SolarMindCoordinator,
            "async_set_self_use",
            new_callable=AsyncMock,
        ) as mock_self_use,
    ):
        coordinator = SolarMindCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        from custom_components.solar_mind import async_setup_services as setup_services
        await setup_services(hass)

        await hass.services.async_call(
            DOMAIN,
            "set_self_use",
            {},
            blocking=True,
        )

        mock_self_use.assert_called_once()


async def test_set_house_from_grid_service(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """set_house_use_grid service sets house from grid (no discharge) mode."""
    entry = _solar_mind_config_entry()
    entry.add_to_hass(hass)

    with (
        patch.object(
            SolarMindCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value=SolarMindData(),
        ),
        patch.object(
            SolarMindCoordinator,
            "async_set_house_from_grid",
            new_callable=AsyncMock,
        ) as mock_house_grid,
    ):
        coordinator = SolarMindCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        from custom_components.solar_mind import async_setup_services as setup_services
        await setup_services(hass)

        await hass.services.async_call(
            DOMAIN,
            "set_house_use_grid",
            {},
            blocking=True,
        )

        mock_house_grid.assert_called_once()


async def test_charge_to_value_service(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """charge_to_value service starts charging to target SOC."""
    entry = _solar_mind_config_entry()
    entry.add_to_hass(hass)

    with (
        patch.object(
            SolarMindCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value=SolarMindData(),
        ),
        patch.object(
            SolarMindCoordinator,
            "async_charge_to_target_soc",
            new_callable=AsyncMock,
        ) as mock_charge_soc,
    ):
        coordinator = SolarMindCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        from custom_components.solar_mind import async_setup_services as setup_services
        await setup_services(hass)

        await hass.services.async_call(
            DOMAIN,
            "charge_to_value",
            {"target_soc": 90, "power_w": 4000},
            blocking=True,
        )

        assert coordinator.target_soc == 90
        assert coordinator.charge_to_soc_power_w == 4000
        mock_charge_soc.assert_called_once()
