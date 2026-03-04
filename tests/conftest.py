"""Pytest configuration and fixtures for Solar Mind tests."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure project root and custom_components are on path for imports
ROOT = Path(__file__).resolve().parent.parent
CUSTOM_COMPONENTS = ROOT / "custom_components"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(CUSTOM_COMPONENTS) not in sys.path:
    sys.path.insert(0, str(CUSTOM_COMPONENTS))

# pytest-homeassistant-custom-component provides enable_custom_integrations when installed
try:
    import pytest_homeassistant_custom_component  # noqa: F401
    pytest_plugins = ["pytest_homeassistant_custom_component"]
    _use_ha_plugin = True
except ImportError:
    pytest_plugins = []
    _use_ha_plugin = False

# When HA plugin is not used, mock homeassistant so unit tests run without full HA
if not _use_ha_plugin:
    _ha_modules = (
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.button",
        "homeassistant.components.number",
        "homeassistant.components.select",
        "homeassistant.components.sensor",
        "homeassistant.config_entries",
        "homeassistant.const",
        "homeassistant.core",
        "homeassistant.data_entry_flow",
        "homeassistant.helpers",
        "homeassistant.helpers.config_validation",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.event",
        "homeassistant.helpers.selector",
        "homeassistant.helpers.typing",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.update_coordinator",
    )
    for mod in _ha_modules:
        if mod not in sys.modules:
            _m = MagicMock()
            sys.modules[mod] = _m
    sys.modules["homeassistant"].__path__ = []
    sys.modules["homeassistant.helpers"].__path__ = []
    sys.modules["homeassistant.helpers.event"].async_track_time_interval = MagicMock()
    sys.modules["homeassistant.core"].callback = lambda f: f
    sys.modules["homeassistant.config_entries"].ConfigEntry = MagicMock()
    sys.modules["homeassistant.const"].CONF_NAME = "name"
    sys.modules["homeassistant.const"].Platform = MagicMock()
    sys.modules["homeassistant.core"].HomeAssistant = MagicMock()
    _flow = sys.modules["homeassistant.data_entry_flow"]
    _flow.FlowResultType = type("FlowResultType", (), {"FORM": "form", "CREATE_ENTRY": "create_entry", "ABORT": "abort"})

# When HA plugin is used, ensure homeassistant.helpers.script exists (HA 2024.3 helpers/__init__.py doesn't export it)
if _use_ha_plugin:
    try:
        import homeassistant.helpers.script as _ha_script  # noqa: F401
        import homeassistant.helpers as _ha_helpers
        if not hasattr(_ha_helpers, "script"):
            setattr(_ha_helpers, "script", _ha_script)
    except ImportError:
        pass


@pytest.fixture
def hass_mock():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()
    hass.states = MagicMock()
    hass.config_entries = MagicMock()
    hass.config.time_zone = "Europe/Prague"
    hass.config.latitude = 50.0
    hass.config.longitude = 14.4
    return hass


@pytest.fixture
def config_entry_mock():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_123"
    entry.title = "Test Solar Mind"
    entry.data = {
        "name": "Test Solar Mind",
        "pv_azimuth": 180,
        "pv_tilt": 35,
        "max_pv_power": 5000,
        "price_mode": "spot",
        "price_sensor": "sensor.spot_price",
        "remotecontrol_power_control": "select.solax_remotecontrol_power_control",
        "remotecontrol_active_power": "number.solax_remotecontrol_active_power",
        "remotecontrol_trigger": "button.solax_remotecontrol_trigger",
        "battery_soc": "sensor.solax_battery_soc",
    }
    entry.options = {}
    return entry


@pytest.fixture
def simulator_config_entry_mock():
    """Create a mock config entry for the simulator."""
    entry = MagicMock()
    entry.entry_id = "test_simulator_123"
    entry.title = "Test Solax Simulator"
    entry.data = {
        "name": "Test Solax Simulator",
        "battery_capacity": 10000,
        "max_pv_power": 10000,
        "max_charge_power": 5000,
        "max_discharge_power": 5000,
        "initial_soc": 50,
    }
    return entry


@pytest.fixture
def make_hourly_prices():
    """Factory fixture to create hourly prices."""
    def _make_prices(
        base_date: datetime | None = None,
        prices: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Create hourly price data.
        
        Args:
            base_date: Start date for prices (defaults to today midnight)
            prices: List of 24 prices for each hour (defaults to synthetic data)
        """
        if base_date is None:
            base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if prices is None:
            # Create realistic Czech price pattern
            # Low at night (2-5), peaks at morning (7-9) and evening (17-20)
            prices = [
                0.02, 0.02, 0.01, 0.01, 0.02, 0.03,  # 0-5 (night - lowest)
                0.05, 0.08, 0.10, 0.08, 0.07, 0.06,  # 6-11 (morning peak)
                0.05, 0.04, 0.04, 0.05, 0.06, 0.12,  # 12-17 (afternoon)
                0.15, 0.14, 0.10, 0.08, 0.06, 0.04,  # 18-23 (evening peak)
            ]
        
        return [
            {"start": base_date + timedelta(hours=i), "price": p}
            for i, p in enumerate(prices)
        ]
    
    return _make_prices


@pytest.fixture
def make_weather_forecast():
    """Factory fixture to create weather forecasts."""
    def _make_forecast(
        base_date: datetime | None = None,
        conditions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Create hourly weather forecast data.
        
        Args:
            base_date: Start date for forecast
            conditions: List of 24 weather conditions
        """
        if base_date is None:
            base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if conditions is None:
            # Default: night, then sunny day
            conditions = (
                ["cloudy"] * 6 +  # Night
                ["partly_cloudy"] * 2 +  # Early morning
                ["sunny"] * 8 +  # Day
                ["partly_cloudy"] * 2 +  # Late afternoon
                ["cloudy"] * 6  # Evening/night
            )
        
        return [
            {
                "datetime": base_date + timedelta(hours=i),
                "condition": cond,
                "temperature": 20 + (5 if 10 <= i <= 16 else 0),
            }
            for i, cond in enumerate(conditions)
        ]
    
    return _make_forecast
