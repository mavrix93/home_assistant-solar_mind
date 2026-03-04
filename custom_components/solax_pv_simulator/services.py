"""Services for the Solax PV Simulator integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SimulatedWeather
from .simulator import SolaxSimulator

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_SET_WEATHER = "set_weather"
SERVICE_SET_SIMULATED_HOUR = "set_simulated_hour"
SERVICE_USE_REAL_TIME = "use_real_time"
SERVICE_SET_BATTERY_SOC = "set_battery_soc"
SERVICE_SET_HOUSE_LOAD = "set_house_load"
SERVICE_RESET_ENERGY = "reset_energy_counters"

# Service schemas
SCHEMA_SET_WEATHER = vol.Schema(
    {
        vol.Required("weather"): vol.In(
            [w.value for w in SimulatedWeather]
        ),
    }
)

SCHEMA_SET_HOUR = vol.Schema(
    {
        vol.Required("hour"): vol.All(vol.Coerce(float), vol.Range(min=0, max=24)),
    }
)

SCHEMA_USE_REAL_TIME = vol.Schema(
    {
        vol.Optional("enabled", default=True): cv.boolean,
    }
)

SCHEMA_SET_SOC = vol.Schema(
    {
        vol.Required("soc"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    }
)

SCHEMA_SET_LOAD = vol.Schema(
    {
        vol.Required("load"): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }
)

SCHEMA_EMPTY = vol.Schema({})


async def async_register_services(hass: HomeAssistant) -> None:
    """Register services for the Solax PV Simulator."""

    async def _get_simulator() -> SolaxSimulator | None:
        """Get the first available simulator."""
        if DOMAIN not in hass.data:
            return None

        for entry_id, simulator in hass.data[DOMAIN].items():
            if isinstance(simulator, SolaxSimulator):
                return simulator

        return None

    async def handle_set_weather(call: ServiceCall) -> None:
        """Handle set weather service call."""
        simulator = await _get_simulator()
        if simulator is None:
            _LOGGER.error("No Solax PV Simulator found")
            return

        weather = call.data["weather"]
        _LOGGER.info("Service call: set weather to %s", weather)
        simulator.set_weather(weather)

    async def handle_set_simulated_hour(call: ServiceCall) -> None:
        """Handle set simulated hour service call."""
        simulator = await _get_simulator()
        if simulator is None:
            _LOGGER.error("No Solax PV Simulator found")
            return

        hour = call.data["hour"]
        _LOGGER.info("Service call: set simulated hour to %s", hour)
        simulator.set_simulated_hour(hour)

    async def handle_use_real_time(call: ServiceCall) -> None:
        """Handle use real time service call."""
        simulator = await _get_simulator()
        if simulator is None:
            _LOGGER.error("No Solax PV Simulator found")
            return

        enabled = call.data.get("enabled", True)
        _LOGGER.info("Service call: use real time = %s", enabled)
        simulator.use_real_time(enabled)

    async def handle_set_battery_soc(call: ServiceCall) -> None:
        """Handle set battery SOC service call."""
        simulator = await _get_simulator()
        if simulator is None:
            _LOGGER.error("No Solax PV Simulator found")
            return

        soc = call.data["soc"]
        _LOGGER.info("Service call: set battery SOC to %s%%", soc)
        simulator.set_battery_soc(soc)

    async def handle_set_house_load(call: ServiceCall) -> None:
        """Handle set house load service call."""
        simulator = await _get_simulator()
        if simulator is None:
            _LOGGER.error("No Solax PV Simulator found")
            return

        load = call.data["load"]
        _LOGGER.info("Service call: set house load to %s W", load)
        simulator.set_house_load(load)

    async def handle_reset_energy(call: ServiceCall) -> None:
        """Handle reset energy counters service call."""
        simulator = await _get_simulator()
        if simulator is None:
            _LOGGER.error("No Solax PV Simulator found")
            return

        _LOGGER.info("Service call: reset energy counters")
        simulator.reset_energy_counters()

    # Register services (only if not already registered)
    if not hass.services.has_service(DOMAIN, SERVICE_SET_WEATHER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_WEATHER,
            handle_set_weather,
            schema=SCHEMA_SET_WEATHER,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_SIMULATED_HOUR):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_SIMULATED_HOUR,
            handle_set_simulated_hour,
            schema=SCHEMA_SET_HOUR,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_USE_REAL_TIME):
        hass.services.async_register(
            DOMAIN,
            SERVICE_USE_REAL_TIME,
            handle_use_real_time,
            schema=SCHEMA_USE_REAL_TIME,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_BATTERY_SOC):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_BATTERY_SOC,
            handle_set_battery_soc,
            schema=SCHEMA_SET_SOC,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_HOUSE_LOAD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_HOUSE_LOAD,
            handle_set_house_load,
            schema=SCHEMA_SET_LOAD,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RESET_ENERGY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_ENERGY,
            handle_reset_energy,
            schema=SCHEMA_EMPTY,
        )
