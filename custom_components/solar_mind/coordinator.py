"""DataUpdateCoordinator for Solar Mind."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AUTOREPEAT_DURATION,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_SOC,
    CONF_ENERGY_STORAGE_MODE,
    CONF_FALLBACK_STRATEGY,
    CONF_MAX_PV_POWER,
    CONF_PASSIVE_DESIRED_GRID_POWER,
    CONF_PASSIVE_UPDATE_TRIGGER,
    CONF_PRICE_SENSOR,
    CONF_PRICE_SOURCE,
    CONF_REMOTECONTROL_ACTIVE_POWER,
    CONF_REMOTECONTROL_AUTOREPEAT_DURATION,
    CONF_REMOTECONTROL_POWER_CONTROL,
    CONF_REMOTECONTROL_TRIGGER,
    CONF_SOLAX_DEVICE_TYPE,
    CONF_STRATEGY_SELECTOR_ENTITY,
    CONF_UPDATE_INTERVAL,
    CONF_WEATHER_ENTITY,
    DEFAULT_AUTOREPEAT_DURATION,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_MAX_PV_POWER,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PriceSource,
    SolaxDeviceType,
    StrategyKey,
)
from .models import (
    EnergyPlan,
    PlanHistory,
    PriceData,
    SolaxState,
    SolarMindData,
    StrategyInput,
    StrategyOutput,
    WeatherForecast,
)
from .planner import EnergyPlanner, record_actual_hour
from .price_adapter import create_price_adapter
from .strategies import get_strategy

_LOGGER = logging.getLogger(__name__)


class SolarMindCoordinator(DataUpdateCoordinator[SolarMindData]):
    """Coordinator to manage Solar Mind data updates and strategy execution."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self._price_adapter = create_price_adapter(
            hass,
            entry.data.get(CONF_PRICE_SOURCE, PriceSource.CZECH_OTE),
        )
        
        # Initialize planner
        self._planner = EnergyPlanner(dict(entry.options))
        
        # Persistent plan history (survives updates)
        self._plan_history = PlanHistory()
        
        # Track last hour we recorded actuals for
        self._last_recorded_hour: datetime | None = None
        
        # Get update interval from options
        update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=update_interval),
        )

    @property
    def device_type(self) -> SolaxDeviceType:
        """Get the configured Solax device type."""
        return SolaxDeviceType(
            self.entry.data.get(CONF_SOLAX_DEVICE_TYPE, SolaxDeviceType.MODBUS_REMOTE)
        )

    async def _async_update_data(self) -> SolarMindData:
        """Fetch data and run strategy."""
        try:
            data = SolarMindData()
            data.last_update = datetime.now(timezone.utc)
            
            # Fetch price data
            data.prices = await self._fetch_prices()
            
            # Fetch weather data
            data.weather = await self._fetch_weather()
            
            # Fetch Solax state
            data.solax_state = await self._fetch_solax_state()
            
            # Determine active strategy
            data.active_strategy = await self._get_active_strategy()
            
            # Run strategy
            strategy_output = await self._run_strategy(data)
            data.strategy_output = strategy_output
            
            # Execute strategy output (apply to Solax)
            await self._execute_strategy(strategy_output)
            
            # Generate energy plan
            data.energy_plan = await self._generate_energy_plan(data)
            
            # Record actual values for historical tracking
            await self._record_actuals(data)
            
            # Attach plan history
            data.plan_history = self._plan_history
            
            # Store system config
            data.battery_capacity_wh = float(
                self.entry.options.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
            )
            data.max_pv_power_w = float(
                self.entry.options.get(CONF_MAX_PV_POWER, DEFAULT_MAX_PV_POWER)
            )
            
            data.last_error = None
            return data
            
        except Exception as err:
            _LOGGER.error("Error updating Solar Mind data: %s", err)
            # Return data with error but don't fail completely
            data = SolarMindData()
            data.last_update = datetime.now(timezone.utc)
            data.last_error = str(err)
            data.plan_history = self._plan_history
            return data
    
    async def _generate_energy_plan(self, data: SolarMindData) -> EnergyPlan | None:
        """Generate energy plan based on current state, prices, and weather."""
        try:
            current_time = datetime.now(timezone.utc)
            current_soc = data.solax_state.battery_soc or 50.0
            
            # Update planner options in case they changed
            self._planner = EnergyPlanner(dict(self.entry.options))
            
            # Create the plan
            plan = self._planner.create_plan(
                current_time=current_time,
                current_soc=current_soc,
                prices=data.prices,
                weather=data.weather,
            )
            
            _LOGGER.debug(
                "Generated energy plan: %d hours, PV: %.1f kWh, Load: %.1f kWh",
                len(plan.entries),
                plan.total_pv_forecast_wh / 1000,
                plan.total_load_forecast_wh / 1000,
            )
            
            return plan
            
        except Exception as e:
            _LOGGER.error("Failed to generate energy plan: %s", e)
            return None
    
    async def _record_actuals(self, data: SolarMindData) -> None:
        """Record actual values for historical comparison."""
        try:
            current_time = datetime.now(timezone.utc)
            current_hour = current_time.replace(minute=0, second=0, microsecond=0)
            
            # Only record once per hour
            if self._last_recorded_hour == current_hour:
                return
            
            # Record previous hour's actuals (we're now in a new hour)
            prev_hour = current_hour - timedelta(hours=1)
            
            # Get previous plan if available
            prev_plan = self.data.energy_plan if self.data else None
            
            # Record the comparison
            record_actual_hour(
                plan_history=self._plan_history,
                energy_plan=prev_plan,
                hour=prev_hour,
                solax_state=data.solax_state,
                price=data.prices.get_price_at(prev_hour),
            )
            
            self._last_recorded_hour = current_hour
            
            _LOGGER.debug(
                "Recorded actuals for hour %s, total history: %d entries",
                prev_hour.strftime("%H:00"),
                len(self._plan_history.comparisons),
            )
            
        except Exception as e:
            _LOGGER.error("Failed to record actuals: %s", e)

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

    async def _resolve_solax_entity_id(self, configured_id: str) -> str | None:
        """Resolve Solax entity; match configured id or base/suffix variants (config or HA may use _2)."""
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
            if entity_id.startswith(configured_id + "_") and entity_id[len(configured_id) + 1 :].isdigit():
                return entity_id
            if entity_id.startswith(base_id + "_") and entity_id[len(base_id) + 1 :].isdigit():
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

    def _parse_forecast_entries(self, forecast_data: list[dict]) -> WeatherForecast:
        """Parse service or attribute forecast list into WeatherForecast."""
        hourly = []
        for entry in forecast_data:
            dt_str = entry.get("datetime")
            if not dt_str:
                # Legacy attribute may use 'datetime' key with different format
                continue
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                hourly.append({
                    "datetime": dt,
                    "condition": entry.get("condition", ""),
                    "temperature": entry.get("temperature"),
                    "precipitation": entry.get("precipitation"),
                })
            except (ValueError, TypeError):
                pass
        return WeatherForecast(hourly=hourly)

    async def _fetch_weather(self) -> WeatherForecast:
        """Fetch weather forecast from configured entity."""
        weather_entity_id = self.entry.data.get(CONF_WEATHER_ENTITY)
        if not weather_entity_id:
            _LOGGER.debug("No weather entity configured")
            return WeatherForecast()

        # Resolve entity id (config or HA may use base or suffix, e.g. weather.open_meteo or weather.open_meteo_2)
        state = self.hass.states.get(weather_entity_id)
        if not state:
            base_id = self._entity_id_strip_suffix(weather_entity_id)
            base_name = base_id.split(".")[-1] if "." in base_id else base_id
            result = self.hass.states.async_entity_ids("weather")
            entity_ids = await result if asyncio.iscoroutine(result) else result
            for entity_id in entity_ids:
                obj = entity_id.split(".", 1)[-1] if "." in entity_id else entity_id
                if obj == base_name or obj.startswith(base_name + "_"):
                    s = self.hass.states.get(entity_id)
                    if s and s.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                        weather_entity_id = entity_id
                        state = s
                        break
        if not state:
            _LOGGER.debug("Weather entity not found (configured: %s)", self.entry.data.get(CONF_WEATHER_ENTITY))
            return WeatherForecast()

        # 1) Try weather.get_forecasts service (HA 2024+)
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
            if response and weather_entity_id in response:
                forecast_data = response[weather_entity_id].get("forecast", [])
                if forecast_data:
                    return self._parse_forecast_entries(forecast_data)
        except Exception as e:
            err_msg = str(e).lower()
            if "not found" not in err_msg and "unknown service" not in err_msg:
                _LOGGER.warning("Could not fetch weather forecast: %s", e)

        # 2) Fallback: legacy forecast attribute on weather entity
        forecast_attr = state.attributes.get("forecast") or state.attributes.get("hourly_forecast")
        if forecast_attr:
            return self._parse_forecast_entries(forecast_attr)

        return WeatherForecast()

    async def _fetch_solax_state(self) -> SolaxState:
        """Fetch current state from Solax entities."""
        solax_state = SolaxState()

        # Battery SOC
        soc_entity_id = self.entry.data.get(CONF_BATTERY_SOC)
        if soc_entity_id:
            resolved = await self._resolve_solax_entity_id(soc_entity_id)
            if resolved:
                state = self.hass.states.get(resolved)
                if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        solax_state.battery_soc = float(state.state)
                    except (ValueError, TypeError):
                        pass

        # Current mode
        if self.device_type == SolaxDeviceType.MODBUS_REMOTE:
            mode_entity_id = self.entry.data.get(CONF_REMOTECONTROL_POWER_CONTROL)
            if mode_entity_id:
                resolved = await self._resolve_solax_entity_id(mode_entity_id)
                if resolved:
                    state = self.hass.states.get(resolved)
                    if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                        solax_state.current_mode = state.state

            # Active power
            power_entity_id = self.entry.data.get(CONF_REMOTECONTROL_ACTIVE_POWER)
            if power_entity_id:
                resolved = await self._resolve_solax_entity_id(power_entity_id)
                if resolved:
                    state = self.hass.states.get(resolved)
                    if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                        try:
                            solax_state.active_power = float(state.state)
                        except (ValueError, TypeError):
                            pass
        else:
            # Passive mode
            power_entity_id = self.entry.data.get(CONF_PASSIVE_DESIRED_GRID_POWER)
            if power_entity_id:
                resolved = await self._resolve_solax_entity_id(power_entity_id)
                if resolved:
                    state = self.hass.states.get(resolved)
                    if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                        try:
                            solax_state.active_power = float(state.state)
                        except (ValueError, TypeError):
                            pass

        return solax_state

    async def _get_active_strategy(self) -> StrategyKey:
        """Determine the active strategy from selector entity or fallback."""
        # Check for strategy selector entity
        selector_entity_id = self.entry.options.get(CONF_STRATEGY_SELECTOR_ENTITY)
        
        if selector_entity_id:
            state = self.hass.states.get(selector_entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                # Try to match state to a strategy key
                strategy_state = state.state.lower().replace(" ", "_")
                try:
                    return StrategyKey(strategy_state)
                except ValueError:
                    # State doesn't match any strategy key, try display name matching
                    from .const import STRATEGY_DISPLAY_NAMES
                    for key, display_name in STRATEGY_DISPLAY_NAMES.items():
                        if state.state.lower() == display_name.lower():
                            return StrategyKey(key)
                    
                    _LOGGER.warning(
                        "Strategy selector state '%s' does not match any strategy", 
                        state.state
                    )
        
        # Fall back to configured default strategy
        fallback = self.entry.options.get(CONF_FALLBACK_STRATEGY, StrategyKey.SPOT_PRICE_WEATHER)
        return StrategyKey(fallback)

    async def _run_strategy(self, data: SolarMindData) -> StrategyOutput:
        """Run the active strategy and return output."""
        try:
            strategy = get_strategy(data.active_strategy.value)
            
            strategy_input = StrategyInput(
                current_time=datetime.now(timezone.utc),
                prices=data.prices,
                weather=data.weather,
                solax_state=data.solax_state,
                options=dict(self.entry.options),
            )
            
            return strategy.compute(strategy_input, dict(self.entry.options))
            
        except Exception as e:
            _LOGGER.error("Strategy execution failed: %s", e)
            from .const import SOLAX_MODE_SELF_USE, SystemStatus
            return StrategyOutput(
                status=SystemStatus.ERROR,
                mode=SOLAX_MODE_SELF_USE,
                reason=f"Strategy error: {e}",
            )

    async def _execute_strategy(self, output: StrategyOutput) -> None:
        """Execute strategy output by calling Solax entities."""
        from .const import SystemStatus
        
        # Don't execute if in error or idle state
        if output.status in (SystemStatus.ERROR, SystemStatus.IDLE):
            _LOGGER.debug("Not executing strategy: status=%s", output.status)
            return
        
        try:
            if self.device_type == SolaxDeviceType.MODBUS_REMOTE:
                await self._execute_modbus_remote(output)
            else:
                await self._execute_passive_sofar(output)
        except Exception as e:
            _LOGGER.error("Failed to execute strategy: %s", e)

    def _entity_available(self, entity_id: str) -> bool:
        """Return True if the entity exists and is available."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    async def _execute_modbus_remote(self, output: StrategyOutput) -> None:
        """Execute strategy using Modbus remote control entities."""
        # Set power control mode
        mode_entity_id = self.entry.data.get(CONF_REMOTECONTROL_POWER_CONTROL)
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
        power_entity_id = self.entry.data.get(CONF_REMOTECONTROL_ACTIVE_POWER)
        if power_entity_id and output.power_w is not None:
            resolved = await self._resolve_solax_entity_id(power_entity_id)
            if resolved and self._entity_available(resolved):
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {"entity_id": resolved, "value": output.power_w},
                )

        # Set autorepeat duration if specified
        duration_entity_id = self.entry.data.get(CONF_REMOTECONTROL_AUTOREPEAT_DURATION)
        duration = output.duration_seconds or self.entry.options.get(
            CONF_AUTOREPEAT_DURATION, DEFAULT_AUTOREPEAT_DURATION
        )
        if duration_entity_id:
            resolved = await self._resolve_solax_entity_id(duration_entity_id)
            if resolved and self._entity_available(resolved):
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {"entity_id": resolved, "value": duration},
                )

        # Trigger the remote control
        trigger_entity_id = self.entry.data.get(CONF_REMOTECONTROL_TRIGGER)
        if trigger_entity_id:
            resolved = await self._resolve_solax_entity_id(trigger_entity_id)
            if resolved and self._entity_available(resolved):
                await self.hass.services.async_call(
                    "button",
                    "press",
                    {"entity_id": resolved},
                )

    async def _execute_passive_sofar(self, output: StrategyOutput) -> None:
        """Execute strategy using Passive mode (Sofar) entities."""
        # Set desired grid power
        # Positive = import from grid, Negative = export to grid
        power_entity_id = self.entry.data.get(CONF_PASSIVE_DESIRED_GRID_POWER)
        if power_entity_id and output.power_w is not None:
            resolved = await self._resolve_solax_entity_id(power_entity_id)
            if resolved and self._entity_available(resolved):
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {"entity_id": resolved, "value": output.power_w},
                )

        # Trigger the update
        trigger_entity_id = self.entry.data.get(CONF_PASSIVE_UPDATE_TRIGGER)
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
        """Manually trigger charge from grid."""
        from .const import SOLAX_MODE_GRID_CONTROL, SystemStatus
        
        output = StrategyOutput(
            status=SystemStatus.CHARGING,
            mode=SOLAX_MODE_GRID_CONTROL,
            power_w=power_w or self.entry.options.get("max_charge_power", 3000),
            duration_seconds=duration_seconds,
            reason="Manual charge from grid",
        )
        await self._execute_strategy(output)

    async def async_discharge_to_grid(
        self, power_w: int | None = None, duration_seconds: int | None = None
    ) -> None:
        """Manually trigger discharge to grid."""
        from .const import SOLAX_MODE_BATTERY_CONTROL, SystemStatus
        
        power = -(power_w or self.entry.options.get("max_discharge_power", 3000))
        output = StrategyOutput(
            status=SystemStatus.DISCHARGING,
            mode=SOLAX_MODE_BATTERY_CONTROL,
            power_w=power,
            duration_seconds=duration_seconds,
            reason="Manual discharge to grid",
        )
        await self._execute_strategy(output)

    async def async_set_self_use(self) -> None:
        """Manually set self-use mode."""
        from .const import SOLAX_MODE_SELF_USE, SystemStatus
        
        output = StrategyOutput(
            status=SystemStatus.SELF_USE,
            mode=SOLAX_MODE_SELF_USE,
            reason="Manual self-use mode",
        )
        await self._execute_strategy(output)

    async def async_set_house_from_grid(self) -> None:
        """Manually set house-from-grid mode (no discharge)."""
        from .const import SOLAX_MODE_NO_DISCHARGE, SystemStatus
        
        output = StrategyOutput(
            status=SystemStatus.HOUSE_FROM_GRID,
            mode=SOLAX_MODE_NO_DISCHARGE,
            reason="Manual house from grid (no discharge)",
        )
        await self._execute_strategy(output)

    async def async_apply_strategy(self) -> None:
        """Manually trigger strategy evaluation and execution."""
        await self.async_refresh()
