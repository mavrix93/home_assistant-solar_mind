"""DataUpdateCoordinator for Solar Mind."""

import asyncio
import json
import logging
import zoneinfo
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.solar_mind.ha.price_adapter import PriceAdapter

from .const import (
    CONF_MAX_PV_POWER,
    CONF_PRICE_SENSOR,
    CONF_PV_AZIMUTH,
    CONF_PV_TILT,
    CONF_REMOTECONTROL_ACTIVE_POWER,
    CONF_REMOTECONTROL_POWER_CONTROL,
    CONF_REMOTECONTROL_TRIGGER,
    DOMAIN,
    StrategyOutput,
    SystemStatus,
)

from ..mind.models import (
    PriceData,
    SolarMindData,
    
)
from ..mind.generation_forecast import ForecastSolarApiGenerationForecast

from ..mind.types import Energy, Timeseries

_LOGGER = logging.getLogger(__name__)



class SolarMindCoordinator(DataUpdateCoordinator[SolarMindData]):
    """Coordinator to manage Solar Mind data updates and strategy execution."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry

        self._price_adapter = PriceAdapter(hass)
        
        # Initialize generation forecast client (forecast.solar API)
        # Use defaults if not configured in options
        azimuth = float(entry.data[CONF_PV_AZIMUTH])
        tilt = float(entry.data[CONF_PV_TILT])
        max_peak_power_kw = float(entry.data[CONF_MAX_PV_POWER]) / 1000.0
        self._generation_forecast_client = ForecastSolarApiGenerationForecast(
            latitude=hass.config.latitude,
            longitude=hass.config.longitude,
            azimuth=azimuth,
            tilt=tilt,
            max_peak_power_kw=max_peak_power_kw,
        )

        # Plan is updated twice per hour (every 30 min); Solax acts every hour
        plan_update_minutes = 30
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=plan_update_minutes),
        )
        self._hourly_execution_unsub: Any = None
    
    def schedule_hourly_execution(self) -> None:
        """Schedule Solax execution at the start of every hour based on plan."""
        if self._hourly_execution_unsub is not None:
            return
        self._hourly_execution_unsub = async_track_time_change(
            self.hass,
            self._execute_plan_for_current_hour,
            minute=0,
            second=0,
        )
        _LOGGER.debug("Scheduled hourly plan execution at :00")
    
    
    async def _execute_plan_for_current_hour(self, now: datetime) -> None:
        """Execute Solax action for the current hour from the plan (runs every hour at :00)."""
        if not self.data or not self.data.plan_actions:
            return
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        action: str | None = None
        for h, a in self.data.plan_actions:
            if h == current_hour:
                action = a
                break
        if action is None:
            _LOGGER.debug("No plan action for hour %s", current_hour.isoformat())
            return
        _LOGGER.debug("Executing plan action for %s: %s", current_hour.isoformat(), action)
        output = self._plan_action_to_strategy_output(action)
        await self._execute_strategy(output)


    async def _fetch_generation_forecast(self) -> Timeseries[Energy] | None:
        """Fetch PV generation forecast from forecast.solar API."""
        try:
            forecast = await self.hass.async_add_executor_job(
                self._generation_forecast_client.get_generation_forecast
            )
            if forecast is None:
                return None
            # Convert naive local timestamps to UTC-aware datetimes
            local_tz = zoneinfo.ZoneInfo(self.hass.config.time_zone)
            utc_points: list[tuple[datetime, float]] = []
            for dt, value in forecast.points:
                local_aware = dt.replace(tzinfo=local_tz)
                utc_dt = local_aware.astimezone(timezone.utc)
                utc_points.append((utc_dt, value))
            return Timeseries(points=utc_points)
        except Exception as e:
            _LOGGER.warning("Failed to fetch generation forecast: %s", e)
            return None

    async def _async_update_data(self) -> SolarMindData:
        """Fetch data and run strategy."""
        try:
            data = SolarMindData()
            data.last_update = datetime.now(timezone.utc)
            
            # Fetch price data
            data.prices = await self._fetch_prices()

            # Fetch generation forecast from forecast.solar API
            data.generation_forecast = await self._fetch_generation_forecast()

            
            data.last_error = None
            return data
            
        except Exception as err:
            _LOGGER.error("Error updating Solar Mind data: %s", err)
            # Return data with error but don't fail completely
            data = SolarMindData()
            data.last_update = datetime.now(timezone.utc)
            data.last_error = str(err)
            return data
    

    @staticmethod
    def _entity_id_strip_suffix(entity_id: str) -> str:
        """Return entity_id with trailing _<digits> stripped from object_id (e.g. sensor.foo_2 -> sensor.foo)."""
        if "." not in entity_id:
            return entity_id
        domain, object_id = entity_id.split(".", 1)
        while object_id and object_id[-1].isdigit():
            idx = object_id.rfind("_")
            if idx < 0 or not object_id[idx + 1 :].isdigit():
                break
            object_id = object_id[:idx]
        return f"{domain}.{object_id}" if object_id else entity_id

    async def _resolve_price_sensor_entity_id(self, configured_id: str) -> str | None:
        """Resolve price sensor; match configured id or base/suffix variants (config or HA may use _2, _3)."""
        state = self.hass.states.get(configured_id)
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return configured_id
        base_id = self._entity_id_strip_suffix(configured_id)
        logical_base = base_id.rsplit(".", 1)[-1] if "." in base_id else base_id
        result = self.hass.states.async_entity_ids("sensor")
        entity_ids = await result if asyncio.iscoroutine(result) else result
        for entity_id in entity_ids:
            s = self.hass.states.get(entity_id)
            if not s or s.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            if "current_spot_electricity_price" not in entity_id:
                continue
            obj = entity_id.split(".", 1)[-1] if "." in entity_id else entity_id
            if obj == logical_base or obj.startswith(logical_base + "_"):
                return entity_id
        return None


    async def _fetch_prices(self) -> PriceData:
        """Fetch and parse price data from configured sensor."""
        price_sensor_id = self.entry.data.get(CONF_PRICE_SENSOR)
        if not price_sensor_id:
            _LOGGER.debug("No price sensor configured")
            return PriceData()

        resolved_id = await self._resolve_price_sensor_entity_id(price_sensor_id)
        if not resolved_id:
            _LOGGER.warning(
                "Price sensor %s is unavailable (check Czech Energy Spot Prices integration)",
                price_sensor_id,
            )
            return PriceData()

        state = self.hass.states.get(resolved_id)
        if state is None:
            return PriceData()
        return self._price_adapter.parse_price_data(state)


    async def _execute_strategy(self, output: StrategyOutput) -> None:
        """Execute strategy output by calling Solax entities."""

        
        _LOGGER.info("Executing strategy: %s", output)
        # try:
        #     if self.device_type == SolaxDeviceType.MODBUS_REMOTE:
        #         await self._execute_modbus_remote(output)
        #     else:
        #         raise NotImplementedError("Passive mode not implemented")
        # except Exception as e:
        #     _LOGGER.error("Failed to execute strategy: %s", e)

    def _entity_available(self, entity_id: str) -> bool:
        """Return True if the entity exists and is available."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    async def _execute_modbus_remote(self, output: StrategyOutput) -> None:
        """Execute strategy using Modbus remote control entities."""
        # Set power control mode
        mode_entity_id = self.entry.data[CONF_REMOTECONTROL_POWER_CONTROL]
        if mode_entity_id and output.mode:
            resolved = await self._resolve_solax_entity_id(mode_entity_id)
            if not resolved:
                _LOGGER.debug(
                    "Skipping select_option: entity %s not available yet",
                    mode_entity_id,
                )
            else:
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {"entity_id": resolved, "option": output.mode},
                )

        # Set active power if specified
        power_entity_id = self.entry.data[CONF_REMOTECONTROL_ACTIVE_POWER]
        if power_entity_id and output.power_w is not None:
            resolved = await self._resolve_solax_entity_id(power_entity_id)
            if resolved and self._entity_available(resolved):
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {"entity_id": resolved, "value": output.power_w},
                )

      

        # Trigger the remote control
        trigger_entity_id = self.entry.data[CONF_REMOTECONTROL_TRIGGER]
        if trigger_entity_id:
            resolved = await self._resolve_solax_entity_id(trigger_entity_id)
            if resolved and self._entity_available(resolved):
                await self.hass.services.async_call(
                    "button",
                    "press",
                    {"entity_id": resolved},
                )


    async def async_charge_from_grid(
        self, power_w: int | None = None, duration_seconds: int | None = None
    ) -> None:
        """Manually trigger charge from grid using Battery Control mode."""
        output = StrategyOutput(
            status=SystemStatus.CHARGING,
            mode="SOLAX_MODE_BATTERY_CONTROL",
            power_w=power_w or self.entry.options.get("max_charge_power", 3000),
            duration_seconds=duration_seconds,
            reason="Manual charge from grid",
        )
        await self._execute_strategy(output)

    async def async_discharge_to_grid(
        self, power_w: int | None = None, duration_seconds: int | None = None
    ) -> None:
        """Manually trigger discharge to grid using Grid Control mode."""
        power = -(power_w or self.entry.options.get("max_discharge_power", 3000))
        output = StrategyOutput(
            status=SystemStatus.DISCHARGING,
            mode="SOLAX_MODE_GRID_CONTROL",
            power_w=power,
            duration_seconds=duration_seconds,
            reason="Manual discharge to grid",
        )
        await self._execute_strategy(output)

    async def async_set_self_use(self) -> None:
        """Manually set self-use mode."""
        
        output = StrategyOutput(
            status=SystemStatus.SELF_USE,
            mode="SOLAX_MODE_SELF_USE",
            reason="Manual self-use mode",
        )
        await self._execute_strategy(output)

    async def async_set_house_from_grid(self) -> None:
        """Manually set house-from-grid mode (no discharge)."""
        
        output = StrategyOutput(
            status=SystemStatus.HOUSE_FROM_GRID,
            mode="SOLAX_MODE_NO_DISCHARGE",
            reason="Manual house from grid (no discharge)",
        )
        await self._execute_strategy(output)

    async def async_apply_strategy(self) -> None:
        """Manually trigger strategy evaluation and execution."""
        await self.async_refresh()
