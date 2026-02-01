"""Core simulator logic for Solax PV Simulator (HA integration layer)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .simulator_core import SimulatorState, SolaxSimulatorCore

__all__ = ["SimulatorState", "SolaxSimulator"]

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=1)


class SolaxSimulator(SolaxSimulatorCore):
    """Simulator for Solax PV inverter (HA integration)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the simulator."""
        config = dict(entry.data) if entry.data else {}
        super().__init__(config)
        self.hass = hass
        self.entry = entry
        self._unsub_timer: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Start the simulator."""
        _LOGGER.info("Starting Solax PV Simulator")
        self._last_update = datetime.now()
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

    @callback
    def _async_update(self, now: datetime) -> None:
        """Update simulator state (called by HA timer)."""
        self.step(now)
