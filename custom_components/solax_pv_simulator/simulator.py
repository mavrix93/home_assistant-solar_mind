"""Core simulator logic for Solax PV Simulator (HA integration layer)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util.dt import utcnow

from .const import (
    CONF_LATITUDE,
    CONF_WEATHER_ENTITY,
    DEFAULT_LATITUDE,
    SimulatedWeather,
)
from .simulator_core import SimulatorState, SolaxSimulatorCore

__all__ = ["SimulatorState", "SolaxSimulator"]

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=1)

# Map Home Assistant weather condition to simulator weather
HA_CONDITION_TO_WEATHER: dict[str, SimulatedWeather] = {
    "sunny": SimulatedWeather.SUNNY,
    "clear": SimulatedWeather.SUNNY,
    "clear-night": SimulatedWeather.NIGHT,
    "partlycloudy": SimulatedWeather.PARTLY_CLOUDY,
    "partly_cloudy": SimulatedWeather.PARTLY_CLOUDY,
    "cloudy": SimulatedWeather.CLOUDY,
    "fog": SimulatedWeather.CLOUDY,
    "haze": SimulatedWeather.PARTLY_CLOUDY,
    "rainy": SimulatedWeather.RAINY,
    "pouring": SimulatedWeather.RAINY,
    "lightning-rainy": SimulatedWeather.RAINY,
    "snowy": SimulatedWeather.RAINY,
    "snowy-rainy": SimulatedWeather.RAINY,
}


class SolaxSimulator(SolaxSimulatorCore):
    """Simulator for Solax PV inverter (HA integration)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the simulator."""
        config = dict(entry.data) if entry.data else {}
        if CONF_LATITUDE not in config:
            config[CONF_LATITUDE] = getattr(
                hass.config, "latitude", DEFAULT_LATITUDE
            )
        super().__init__(config)
        self.hass = hass
        self.entry = entry
        self._unsub_timer: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Start the simulator."""
        _LOGGER.info("Starting Solax PV Simulator")
        self._last_update = utcnow()
        self._unsub_timer = async_track_time_interval(
            self.hass,
            self._async_update,
            UPDATE_INTERVAL,
        )

    async def async_stop(self) -> None:
        """Stop the simulator."""
        _LOGGER.info("Stopping Solax PV Simulator")
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    def _sync_weather_from_ha(self) -> None:
        """Update simulator weather from configured HA weather entity."""
        entity_id = self.entry.data.get(CONF_WEATHER_ENTITY)
        if not entity_id:
            return
        state = self.hass.states.get(entity_id)
        if not state or not state.state:
            return
        condition = (state.state or "").lower().strip()
        weather = HA_CONDITION_TO_WEATHER.get(
            condition, SimulatedWeather.PARTLY_CLOUDY
        )
        if weather != self.state.weather:
            self.set_weather(weather)

    @callback
    def _async_update(self, now: datetime) -> None:
        """Update simulator state (called by HA timer)."""
        self._sync_weather_from_ha()
        self.step(now)
