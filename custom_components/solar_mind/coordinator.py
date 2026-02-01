"""DataUpdateCoordinator for Solar Mind."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AUTOREPEAT_DURATION,
    CONF_BATTERY_SOC,
    CONF_ENERGY_STORAGE_MODE,
    CONF_FALLBACK_STRATEGY,
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
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PriceSource,
    SolaxDeviceType,
    StrategyKey,
)
from .models import (
    PriceData,
    SolaxState,
    SolarMindData,
    StrategyInput,
    StrategyOutput,
    WeatherForecast,
)
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
            data.last_update = datetime.now()
            
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
            
            data.last_error = None
            return data
            
        except Exception as err:
            _LOGGER.error("Error updating Solar Mind data: %s", err)
            # Return data with error but don't fail completely
            data = SolarMindData()
            data.last_update = datetime.now()
            data.last_error = str(err)
            return data

    async def _fetch_prices(self) -> PriceData:
        """Fetch and parse price data from configured sensor."""
        price_sensor_id = self.entry.data.get(CONF_PRICE_SENSOR)
        if not price_sensor_id:
            _LOGGER.debug("No price sensor configured")
            return PriceData()
        
        state = self.hass.states.get(price_sensor_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning("Price sensor %s is unavailable", price_sensor_id)
            return PriceData()
        
        return self._price_adapter.parse_price_data(state)

    async def _fetch_weather(self) -> WeatherForecast:
        """Fetch weather forecast from configured entity."""
        weather_entity_id = self.entry.data.get(CONF_WEATHER_ENTITY)
        if not weather_entity_id:
            _LOGGER.debug("No weather entity configured")
            return WeatherForecast()
        
        try:
            # Use weather.get_forecasts service
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
            
            if response and weather_entity_id in response:
                forecast_data = response[weather_entity_id].get("forecast", [])
                # Convert to our format
                hourly = []
                for entry in forecast_data:
                    dt_str = entry.get("datetime")
                    if dt_str:
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
                
        except Exception as e:
            _LOGGER.warning("Could not fetch weather forecast: %s", e)
        
        return WeatherForecast()

    async def _fetch_solax_state(self) -> SolaxState:
        """Fetch current state from Solax entities."""
        solax_state = SolaxState()
        
        # Battery SOC
        soc_entity_id = self.entry.data.get(CONF_BATTERY_SOC)
        if soc_entity_id:
            state = self.hass.states.get(soc_entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    solax_state.battery_soc = float(state.state)
                except (ValueError, TypeError):
                    pass
        
        # Current mode
        if self.device_type == SolaxDeviceType.MODBUS_REMOTE:
            mode_entity_id = self.entry.data.get(CONF_REMOTECONTROL_POWER_CONTROL)
            if mode_entity_id:
                state = self.hass.states.get(mode_entity_id)
                if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    solax_state.current_mode = state.state
            
            # Active power
            power_entity_id = self.entry.data.get(CONF_REMOTECONTROL_ACTIVE_POWER)
            if power_entity_id:
                state = self.hass.states.get(power_entity_id)
                if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        solax_state.active_power = float(state.state)
                    except (ValueError, TypeError):
                        pass
        else:
            # Passive mode
            power_entity_id = self.entry.data.get(CONF_PASSIVE_DESIRED_GRID_POWER)
            if power_entity_id:
                state = self.hass.states.get(power_entity_id)
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
                current_time=datetime.now(),
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

    async def _execute_modbus_remote(self, output: StrategyOutput) -> None:
        """Execute strategy using Modbus remote control entities."""
        # Set power control mode
        mode_entity_id = self.entry.data.get(CONF_REMOTECONTROL_POWER_CONTROL)
        if mode_entity_id and output.mode:
            await self.hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": mode_entity_id, "option": output.mode},
            )
        
        # Set active power if specified
        power_entity_id = self.entry.data.get(CONF_REMOTECONTROL_ACTIVE_POWER)
        if power_entity_id and output.power_w is not None:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": power_entity_id, "value": output.power_w},
            )
        
        # Set autorepeat duration if specified
        duration_entity_id = self.entry.data.get(CONF_REMOTECONTROL_AUTOREPEAT_DURATION)
        duration = output.duration_seconds or self.entry.options.get(
            CONF_AUTOREPEAT_DURATION, DEFAULT_AUTOREPEAT_DURATION
        )
        if duration_entity_id:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": duration_entity_id, "value": duration},
            )
        
        # Trigger the remote control
        trigger_entity_id = self.entry.data.get(CONF_REMOTECONTROL_TRIGGER)
        if trigger_entity_id:
            await self.hass.services.async_call(
                "button",
                "press",
                {"entity_id": trigger_entity_id},
            )

    async def _execute_passive_sofar(self, output: StrategyOutput) -> None:
        """Execute strategy using Passive mode (Sofar) entities."""
        # Set desired grid power
        # Positive = import from grid, Negative = export to grid
        power_entity_id = self.entry.data.get(CONF_PASSIVE_DESIRED_GRID_POWER)
        if power_entity_id and output.power_w is not None:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": power_entity_id, "value": output.power_w},
            )
        
        # Trigger the update
        trigger_entity_id = self.entry.data.get(CONF_PASSIVE_UPDATE_TRIGGER)
        if trigger_entity_id:
            await self.hass.services.async_call(
                "button",
                "press",
                {"entity_id": trigger_entity_id},
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
