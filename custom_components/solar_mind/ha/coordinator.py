"""DataUpdateCoordinator for Solar Mind."""

import asyncio
import json
import logging
import zoneinfo
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
import uuid

if TYPE_CHECKING:
    from ..calendar import SolarMindCalendar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback as ha_callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.solar_mind.ha.price_adapter import PriceAdapter

from .const import (
    CONF_BATTERY_SOC,
    CONF_FIXED_HIGH_PRICE,
    CONF_FIXED_LOW_PRICE,
    CONF_MAX_PV_POWER,
    CONF_PRICE_MODE,
    CONF_PRICE_SENSOR,
    CONF_PV_AZIMUTH,
    CONF_PV_TILT,
    CONF_REMOTECONTROL_ACTIVE_POWER,
    CONF_REMOTECONTROL_AUTOREPEAT_DURATION,
    CONF_REMOTECONTROL_POWER_CONTROL,
    CONF_REMOTECONTROL_TRIGGER,
    DOMAIN,
    PriceMode,
    StrategyOutput,
    SystemStatus,
)

from ..mind.fixed_tariff import build_fixed_price_data
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
        self.calendar: SolarMindCalendar | None = None

        self._last_generation_forecast: Timeseries[Energy] | None = None

        # Charge-to-target-SOC state
        self._target_soc: int = 80
        self._charge_to_soc_power_w: int = 5000
        self._charge_to_soc_duration_s: int = 3600
        self._charging_to_soc_active: bool = False
        self._charge_to_soc_status: str = "Idle"
        self._soc_listener_unsub: Any = None
    
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
            self._last_generation_forecast = Timeseries(points=utc_points)
            return self._last_generation_forecast
        except Exception as e:
            _LOGGER.warning("Failed to fetch generation forecast: %s", e)
            return self._last_generation_forecast

    async def _async_update_data(self) -> SolarMindData:
        """Fetch data and run strategy."""
        try:
            data = SolarMindData()
            data.last_update = datetime.now(timezone.utc)
            data.price_mode = self.entry.data.get(CONF_PRICE_MODE, PriceMode.SPOT)

            # Fetch price data
            data.prices = await self._fetch_prices()

            # Fetch generation forecast from forecast.solar API
            data.generation_forecast = await self._fetch_generation_forecast()

            
            # Copy charge-to-SOC state
            data.charge_to_soc_status = self._charge_to_soc_status
            data.charge_to_soc_target = self._target_soc
            data.charge_to_soc_active = self._charging_to_soc_active

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
        """Fetch and parse price data from configured sensor or fixed tariff."""
        price_mode = self.entry.data.get(CONF_PRICE_MODE, PriceMode.SPOT)

        if price_mode == PriceMode.FIXED:
            high = float(self.entry.data.get(CONF_FIXED_HIGH_PRICE, 6.0))
            low = float(self.entry.data.get(CONF_FIXED_LOW_PRICE, 2.5))
            return build_fixed_price_data(high_price=high, low_price=low)

        # Spot price mode – read from sensor
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
        try:
            await self._execute_modbus_remote(output)
        except Exception as e:
            _LOGGER.error("Failed to execute strategy: %s", e)

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

        # Set autorepeat duration if configured
        autorepeat_entity_id = self.entry.data.get(CONF_REMOTECONTROL_AUTOREPEAT_DURATION)
        if autorepeat_entity_id:
            resolved = await self._resolve_solax_entity_id(autorepeat_entity_id)
            if resolved and self._entity_available(resolved):
                duration = output.duration_seconds or self.entry.options.get(
                    "autorepeat_duration", 3600
                )
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {"entity_id": resolved, "value": duration},
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


    def record_calendar_event(self, summary: str, duration_seconds: int | None = None) -> None:
        """Record an event on the calendar entity for the current hour."""
        if self.calendar is None:
            _LOGGER.debug("No calendar entity registered, skipping event recording")
            return
        now = datetime.now(timezone.utc)
        start = now.replace(minute=0, second=0, microsecond=0)
        if duration_seconds:
            end = start + timedelta(seconds=duration_seconds)
        else:
            end = start + timedelta(hours=1)
        self.calendar.add_event(summary=summary, start=start, end=end)

    async def async_charge_from_grid(
        self, power_w: int | None = None, duration_seconds: int | None = None
    ) -> None:
        """Manually trigger charge from grid using Battery Control mode."""
        output = StrategyOutput(
            status=SystemStatus.CHARGING,
            mode="Enabled Battery Control",
            power_w=power_w or self.entry.options.get("max_charge_power", 3000),
            duration_seconds=duration_seconds,
            reason="Manual charge from grid",
        )
        await self._execute_strategy(output)
        self.record_calendar_event("Charging", duration_seconds)

    async def async_discharge_to_grid(
        self, power_w: int | None = None, duration_seconds: int | None = None
    ) -> None:
        """Manually trigger discharge to grid using Grid Control mode."""
        power = -(power_w or self.entry.options.get("max_discharge_power", 3000))
        output = StrategyOutput(
            status=SystemStatus.DISCHARGING,
            mode="Enabled Grid Control",
            power_w=power,
            duration_seconds=duration_seconds,
            reason="Manual discharge to grid",
        )
        await self._execute_strategy(output)

    async def async_set_self_use(self) -> None:
        """Manually set self-use mode."""
        
        output = StrategyOutput(
            status=SystemStatus.SELF_USE,
            mode="Enabled Self Use",
            reason="Manual self-use mode",
        )
        await self._execute_strategy(output)

    async def async_set_house_from_grid(self) -> None:
        """Manually set house-from-grid mode (no discharge)."""

        output = StrategyOutput(
            status=SystemStatus.HOUSE_FROM_GRID,
            mode="Enabled No Discharge",
            reason="Manual house from grid (no discharge)",
        )
        await self._execute_strategy(output)

    async def async_stop_discharge(self) -> None:
        """Stop battery discharge by setting 'Enabled No Discharge' mode."""
        output = StrategyOutput(
            status=SystemStatus.HOUSE_FROM_GRID,
            mode="Enabled No Discharge",
            reason="Stop discharge",
        )
        await self._execute_strategy(output)

    async def async_apply_strategy(self) -> None:
        """Manually trigger strategy evaluation and execution."""
        await self.async_refresh()

    # ── Charge-to-target-SOC ──────────────────────────────────────────

    @property
    def target_soc(self) -> int:
        """Return the current target SOC percentage."""
        return self._target_soc

    @target_soc.setter
    def target_soc(self, value: int) -> None:
        """Set the target SOC percentage."""
        self._target_soc = max(10, min(100, value))

    @property
    def charge_to_soc_power_w(self) -> int:
        """Return the charging power in watts for charge-to-SOC."""
        return self._charge_to_soc_power_w

    @charge_to_soc_power_w.setter
    def charge_to_soc_power_w(self, value: int) -> None:
        """Set the charging power in watts for charge-to-SOC."""
        self._charge_to_soc_power_w = max(100, min(15000, value))

    @property
    def charge_to_soc_duration_s(self) -> int:
        """Return the trigger duration in seconds for charge-to-SOC."""
        return self._charge_to_soc_duration_s

    @charge_to_soc_duration_s.setter
    def charge_to_soc_duration_s(self, value: int) -> None:
        """Set the trigger duration in seconds for charge-to-SOC."""
        self._charge_to_soc_duration_s = max(300, min(86400, value))

    @property
    def charge_to_soc_status(self) -> str:
        """Return the current charge-to-SOC status string."""
        return self._charge_to_soc_status

    @property
    def charging_to_soc_active(self) -> bool:
        """Return whether charge-to-SOC is currently in progress."""
        return self._charging_to_soc_active

    def _get_current_battery_soc(self) -> float | None:
        """Read the current battery SOC from the configured sensor entity."""
        soc_entity_id = self.entry.data.get(CONF_BATTERY_SOC)
        if not soc_entity_id:
            return None
        state = self.hass.states.get(soc_entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    async def async_charge_to_target_soc(self) -> None:
        """Start charging from grid and monitor SOC until target is reached."""
        soc_entity_id = self.entry.data.get(CONF_BATTERY_SOC)
        if not soc_entity_id:
            _LOGGER.error("Cannot charge to target SOC: no battery SOC sensor configured")
            self._charge_to_soc_status = "Error: No SOC sensor"
            self._sync_charge_to_soc_data()
            return

        current_soc = self._get_current_battery_soc()
        if current_soc is not None and current_soc >= self._target_soc:
            _LOGGER.info(
                "Battery SOC (%.1f%%) already at or above target (%d%%), skipping",
                current_soc, self._target_soc,
            )
            self._charge_to_soc_status = (
                f"Already at {current_soc:.0f}% (target {self._target_soc}%)"
            )
            self._sync_charge_to_soc_data()
            return

        # Cancel any existing charge-to-SOC in progress
        await self.async_cancel_charge_to_soc()

        self._charging_to_soc_active = True
        self._charge_to_soc_status = f"Charging to {self._target_soc}%"
        _LOGGER.info(
            "Starting charge to target SOC %d%% (power=%dW, duration=%ds)",
            self._target_soc, self._charge_to_soc_power_w, self._charge_to_soc_duration_s,
        )

        # Use "Enabled Power Control" mode for charge-to-value
        output = StrategyOutput(
            status=SystemStatus.CHARGING_TO_SOC,
            mode="Enabled Power Control",
            power_w=self._charge_to_soc_power_w,
            duration_seconds=self._charge_to_soc_duration_s,
            reason=f"Charge to {self._target_soc}%",
        )
        await self._execute_strategy(output)
        self.record_calendar_event(
            f"Charging to {self._target_soc}%", self._charge_to_soc_duration_s
        )

        # Register listener for battery SOC state changes
        self._soc_listener_unsub = async_track_state_change_event(
            self.hass,
            [soc_entity_id],
            self._handle_soc_state_change,
        )
        self._sync_charge_to_soc_data()

    @ha_callback
    def _handle_soc_state_change(self, event: Event) -> None:
        """Handle battery SOC state change during charge-to-SOC."""
        if not self._charging_to_soc_active:
            return

        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        try:
            current_soc = float(new_state.state)
        except (ValueError, TypeError):
            return

        _LOGGER.debug(
            "Charge-to-SOC: current=%.1f%%, target=%d%%",
            current_soc, self._target_soc,
        )
        self._charge_to_soc_status = (
            f"Charging to {self._target_soc}% (now {current_soc:.0f}%)"
        )

        if current_soc >= self._target_soc:
            _LOGGER.info(
                "Target SOC %d%% reached (current: %.1f%%). Switching to self-use.",
                self._target_soc, current_soc,
            )
            self.hass.async_create_task(self._finish_charge_to_soc(current_soc))
        else:
            self._sync_charge_to_soc_data()

    async def _finish_charge_to_soc(self, final_soc: float) -> None:
        """Stop charging and clean up after target SOC is reached."""
        await self.async_stop_discharge()

        if self._soc_listener_unsub is not None:
            self._soc_listener_unsub()
            self._soc_listener_unsub = None

        self._charging_to_soc_active = False
        self._charge_to_soc_status = f"Target reached ({final_soc:.0f}%)"

        self.record_calendar_event(f"Charged to {final_soc:.0f}%")
        self._sync_charge_to_soc_data()
        _LOGGER.info("Charge-to-SOC completed, now in self-use mode")

    async def async_cancel_charge_to_soc(self) -> None:
        """Cancel any in-progress charge-to-SOC operation."""
        if not self._charging_to_soc_active:
            return

        _LOGGER.info("Cancelling charge-to-SOC")
        if self._soc_listener_unsub is not None:
            self._soc_listener_unsub()
            self._soc_listener_unsub = None

        self._charging_to_soc_active = False
        self._charge_to_soc_status = "Cancelled"
        await self.async_stop_discharge()
        self._sync_charge_to_soc_data()

    def _sync_charge_to_soc_data(self) -> None:
        """Copy charge-to-SOC state into coordinator data and notify entities."""
        if self.data is not None:
            self.data.charge_to_soc_status = self._charge_to_soc_status
            self.data.charge_to_soc_target = self._target_soc
            self.data.charge_to_soc_active = self._charging_to_soc_active
            self.async_set_updated_data(self.data)

    async def _resolve_solax_entity_id(self, configured_id: str) -> str | None:
        """Resolve Solax entity; match configured id or base/suffix variants."""
        state = self.hass.states.get(configured_id)
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return configured_id
        if "." not in configured_id:
            return None
        domain, _ = configured_id.split(".", 1)
        base_id = self._entity_id_strip_suffix(configured_id)
        result = self.hass.states.async_entity_ids(domain)
        entity_ids = await result if asyncio.iscoroutine(result) else result
        for entity_id in entity_ids:
            s = self.hass.states.get(entity_id)
            if not s or s.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            if entity_id == configured_id or entity_id == base_id:
                return entity_id
            stripped = self._entity_id_strip_suffix(entity_id)
            if stripped == base_id:
                return entity_id
        return None
