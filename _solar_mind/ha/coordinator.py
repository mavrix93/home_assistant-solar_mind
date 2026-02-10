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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.solar_mind.const import (
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
    CONF_PV_AZIMUTH,
    CONF_PV_TILT,
    CONF_REMOTECONTROL_ACTIVE_POWER,
    CONF_REMOTECONTROL_AUTOREPEAT_DURATION,
    CONF_REMOTECONTROL_POWER_CONTROL,
    CONF_REMOTECONTROL_TRIGGER,
    CONF_SOLAX_DEVICE_TYPE,
    CONF_STRATEGY_SELECTOR_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_AUTOREPEAT_DURATION,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_MAX_PV_POWER,
    DEFAULT_PV_AZIMUTH,
    DEFAULT_PV_TILT,
    DOMAIN,
    SOLAX_MODE_BATTERY_CONTROL,
    SOLAX_MODE_GRID_CONTROL,
    SOLAX_MODE_NO_DISCHARGE,
    SOLAX_MODE_POWER_CONTROL,
    SOLAX_MODE_SELF_USE,
    STRATEGY_DISPLAY_NAMES,
    PriceSource,
    SolaxDeviceType,
    StrategyKey,
    SystemStatus,
)
from custom_components.solar_mind.ha.plan_adapter import create_plan_from_ha_data
from custom_components.solar_mind.mind.models import (
    AwayPeriod,
    EnergyPlan,
    EventLog,
    EventSeverity,
    EventType,
    Milestone,
    PlannedAction,
    PlanHistory,
    PriceData,
    SolaxState,
    SolarMindData,
    StrategyInput,
    StrategyOutput,
    SystemEvent,
    SystemHealth,
    UserPreferences,
    WeatherForecast,
)
from custom_components.solar_mind.mind.generation_forecast import ForecastSolarApiGenerationForecast
from custom_components.solar_mind.mind.planner import EnergyPlanner, record_actual_hour
from custom_components.solar_mind.mind.types import Energy, Timeseries
from custom_components.solar_mind.ha.price_adapter import create_price_adapter
from custom_components.solar_mind.mind.strategies import get_strategy

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
        
        # Persistent data (survives updates)
        self._plan_history = PlanHistory()
        self._event_log = EventLog()
        self._user_preferences = UserPreferences()
        self._system_health = SystemHealth()
        
        # Track state for event detection
        self._last_recorded_hour: datetime | None = None
        self._last_status: str | None = None
        self._last_strategy: str | None = None
        self._last_weather_condition: str | None = None
        self._last_battery_soc: float | None = None
        self._daily_charge_cycles: int = 0
        self._daily_discharge_cycles: int = 0
        self._daily_mode_changes: int = 0
        self._last_reset_date: datetime | None = None
        
        # Initialize generation forecast client (forecast.solar API)
        azimuth = float(entry.options.get(CONF_PV_AZIMUTH, DEFAULT_PV_AZIMUTH))
        tilt = float(entry.options.get(CONF_PV_TILT, DEFAULT_PV_TILT))
        max_peak_power_kw = float(entry.options.get(CONF_MAX_PV_POWER, DEFAULT_MAX_PV_POWER)) / 1000.0
        self._generation_forecast_client = ForecastSolarApiGenerationForecast(
            latitude=hass.config.latitude,
            longitude=hass.config.longitude,
            azimuth=azimuth,
            tilt=tilt,
            max_peak_power_kw=max_peak_power_kw,
        )

        # Load persisted data
        self._storage_path = Path(hass.config.path(".storage")) / f"{DOMAIN}_{entry.entry_id}.json"
        self._load_persisted_data()
        
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
    
    def _plan_action_to_strategy_output(self, action: str) -> StrategyOutput:
        """Map plan action (CHARGE/SELL/BATTERY_USE/GRID_USE) to StrategyOutput."""
        max_charge = int(self.entry.options.get("max_charge_power", 3000))
        max_discharge = int(self.entry.options.get("max_discharge_power", 3000))
        if action == "CHARGE":
            # Charge from grid: use Battery Control mode with positive power
            # positive=charge, negative=discharge in Battery Control mode
            return StrategyOutput(
                status=SystemStatus.CHARGING,
                mode=SOLAX_MODE_BATTERY_CONTROL,
                power_w=max_charge,
                reason="Plan: charge from grid",
            )
        if action == "SELL":
            # Discharge to grid: use Grid Control mode with negative power
            # positive=import from grid, negative=export to grid in Grid Control mode
            return StrategyOutput(
                status=SystemStatus.DISCHARGING,
                mode=SOLAX_MODE_GRID_CONTROL,
                power_w=-max_discharge,
                reason="Plan: discharge to grid",
            )
        if action == "BATTERY_USE":
            return StrategyOutput(
                status=SystemStatus.SELF_USE,
                mode=SOLAX_MODE_SELF_USE,
                reason="Plan: battery use",
            )
        if action == "GRID_USE":
            return StrategyOutput(
                status=SystemStatus.HOUSE_FROM_GRID,
                mode=SOLAX_MODE_NO_DISCHARGE,
                reason="Plan: grid use",
            )
        return StrategyOutput(
            status=SystemStatus.IDLE,
            mode=SOLAX_MODE_SELF_USE,
            reason="Plan: unknown",
        )
    
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
    
    def _load_persisted_data(self) -> None:
        """Load persisted data from storage."""
        try:
            if self._storage_path.exists():
                with open(self._storage_path, "r") as f:
                    data = json.load(f)
                
                # Load user preferences
                if "user_preferences" in data:
                    prefs = data["user_preferences"]
                    self._user_preferences.preferred_charge_times = prefs.get("preferred_charge_times", [])
                    self._user_preferences.avoid_discharge_times = prefs.get("avoid_discharge_times", [])
                    self._user_preferences.high_demand_appliances = prefs.get("high_demand_appliances", {})
                    
                    # Load away periods
                    for ap in prefs.get("away_periods", []):
                        try:
                            period = AwayPeriod(
                                id=ap["id"],
                                start=datetime.fromisoformat(ap["start"]),
                                end=datetime.fromisoformat(ap["end"]),
                                label=ap.get("label", ""),
                                reduce_load_percent=ap.get("reduce_load_percent", 50.0),
                            )
                            self._user_preferences.away_periods.append(period)
                        except (KeyError, ValueError) as e:
                            _LOGGER.warning("Failed to load away period: %s", e)
                
                _LOGGER.debug("Loaded persisted data from %s", self._storage_path)
        except Exception as e:
            _LOGGER.warning("Failed to load persisted data: %s", e)
    
    async def _save_persisted_data(self) -> None:
        """Save data that should persist across restarts."""
        try:
            data = {
                "user_preferences": self._user_preferences.to_dict(),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "w") as f:
                json.dump(data, f, indent=2)
            
            _LOGGER.debug("Saved persisted data to %s", self._storage_path)
        except Exception as e:
            _LOGGER.warning("Failed to save persisted data: %s", e)
    
    def _add_event(
        self,
        event_type: EventType,
        severity: EventSeverity,
        title: str,
        description: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Add a system event to the log."""
        event = SystemEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            severity=severity,
            title=title,
            description=description,
            data=data or {},
        )
        self._event_log.add_event(event)
        _LOGGER.debug("Event: %s - %s", title, description)
    
    def _reset_daily_counters(self) -> None:
        """Reset daily counters if it's a new day."""
        now = datetime.now(timezone.utc)
        if self._last_reset_date is None or self._last_reset_date.date() != now.date():
            self._daily_charge_cycles = 0
            self._daily_discharge_cycles = 0
            self._daily_mode_changes = 0
            self._last_reset_date = now
    
    def _detect_events(self, data: SolarMindData) -> None:
        """Detect and log system events based on state changes."""
        now = datetime.now(timezone.utc)
        
        # Reset daily counters if needed
        self._reset_daily_counters()
        
        # Status change events
        current_status = data.strategy_output.status.value if data.strategy_output else None
        if current_status and current_status != self._last_status:
            self._daily_mode_changes += 1
            
            if current_status == "charging":
                self._daily_charge_cycles += 1
                self._add_event(
                    EventType.CHARGE_STARTED,
                    EventSeverity.INFO,
                    "Battery charging started",
                    f"Charging from grid at {data.strategy_output.power_w or 0}W",
                    {"power_w": data.strategy_output.power_w if data.strategy_output else None},
                )
            elif self._last_status == "charging":
                self._add_event(
                    EventType.CHARGE_COMPLETED,
                    EventSeverity.SUCCESS,
                    "Battery charging completed",
                    f"Battery SOC: {data.solax_state.battery_soc or 0:.0f}%",
                    {"soc": data.solax_state.battery_soc},
                )
            
            if current_status == "discharging":
                self._daily_discharge_cycles += 1
                self._add_event(
                    EventType.DISCHARGE_STARTED,
                    EventSeverity.INFO,
                    "Battery discharge started",
                    f"Discharging to grid at {abs(data.strategy_output.power_w or 0)}W",
                    {"power_w": data.strategy_output.power_w if data.strategy_output else None},
                )
            elif self._last_status == "discharging":
                self._add_event(
                    EventType.DISCHARGE_COMPLETED,
                    EventSeverity.SUCCESS,
                    "Battery discharge completed",
                    f"Battery SOC: {data.solax_state.battery_soc or 0:.0f}%",
                    {"soc": data.solax_state.battery_soc},
                )
            
            self._last_status = current_status
        
        # Strategy change events
        current_strategy = data.active_strategy.value
        if current_strategy != self._last_strategy and self._last_strategy is not None:
            self._add_event(
                EventType.STRATEGY_CHANGED,
                EventSeverity.INFO,
                "Strategy changed",
                f"Changed from {self._last_strategy} to {current_strategy}",
                {"old": self._last_strategy, "new": current_strategy},
            )
        self._last_strategy = current_strategy
        
        # Battery level events
        soc = data.solax_state.battery_soc
        if soc is not None:
            max_soc = float(self.entry.options.get("max_soc", 95))
            min_soc = float(self.entry.options.get("min_soc", 10))
            
            if soc >= max_soc and (self._last_battery_soc is None or self._last_battery_soc < max_soc):
                self._add_event(
                    EventType.BATTERY_FULL,
                    EventSeverity.SUCCESS,
                    "Battery fully charged",
                    f"Battery reached {soc:.0f}% SOC - preserving for later use",
                    {"soc": soc},
                )
            elif soc <= min_soc and (self._last_battery_soc is None or self._last_battery_soc > min_soc):
                self._add_event(
                    EventType.BATTERY_LOW,
                    EventSeverity.WARNING,
                    "Battery low",
                    f"Battery at {soc:.0f}% SOC - switching to grid",
                    {"soc": soc},
                )
            self._last_battery_soc = soc
        
        # Weather change events
        if data.weather.hourly:
            current_condition = data.weather.hourly[0].get("condition", "").lower() if data.weather.hourly else None
            if current_condition and current_condition != self._last_weather_condition and self._last_weather_condition is not None:
                self._add_event(
                    EventType.WEATHER_CHANGED,
                    EventSeverity.INFO,
                    "Weather forecast changed",
                    f"Conditions changed from {self._last_weather_condition} to {current_condition} - updating strategy",
                    {"old": self._last_weather_condition, "new": current_condition},
                )
            self._last_weather_condition = current_condition
        
        # Price spike/drop events
        if data.prices.current_price is not None and data.prices.today:
            avg_price = sum(p.price for p in data.prices.today) / len(data.prices.today)
            if data.prices.current_price > avg_price * 1.5:
                self._add_event(
                    EventType.PRICE_SPIKE,
                    EventSeverity.WARNING,
                    "High electricity price",
                    f"Current price {data.prices.current_price:.3f} is 50%+ above average",
                    {"price": data.prices.current_price, "avg": avg_price},
                )
            elif data.prices.current_price < avg_price * 0.5:
                self._add_event(
                    EventType.PRICE_DROP,
                    EventSeverity.SUCCESS,
                    "Low electricity price",
                    f"Current price {data.prices.current_price:.3f} is 50%+ below average - good time to charge",
                    {"price": data.prices.current_price, "avg": avg_price},
                )
        
        # Error events
        if data.last_error:
            self._add_event(
                EventType.SYSTEM_ERROR,
                EventSeverity.ERROR,
                "System error",
                data.last_error,
                {"error": data.last_error},
            )
            self._system_health.add_error(data.last_error)
        
        # Update system health counters
        self._system_health.charge_cycles_today = self._daily_charge_cycles
        self._system_health.discharge_cycles_today = self._daily_discharge_cycles
        self._system_health.mode_changes_today = self._daily_mode_changes
        self._system_health.last_inverter_response = now
    
    def _calculate_milestones(self, data: SolarMindData) -> list[Milestone]:
        """Calculate upcoming milestones and recommendations."""
        milestones: list[Milestone] = []
        now = datetime.now(timezone.utc)
        
        if not data.energy_plan or not data.energy_plan.entries:
            return milestones
        
        # Find when energy surplus starts
        for entry in data.energy_plan.entries:
            if entry.hour > now and entry.pv_forecast_wh > entry.load_forecast_wh:
                surplus_wh = entry.pv_forecast_wh - entry.load_forecast_wh
                milestones.append(Milestone(
                    timestamp=entry.hour,
                    milestone_type="surplus_start",
                    title="Energy surplus expected",
                    description=f"PV generation will exceed consumption by {surplus_wh:.0f}Wh",
                    priority=3,
                    data={"surplus_wh": surplus_wh, "pv_wh": entry.pv_forecast_wh},
                ))
                break
        
        # Find best time to run high-demand appliances
        appliances = self._user_preferences.high_demand_appliances
        if appliances:
            for appliance_name, power_w in appliances.items():
                best_entry = None
                best_score = -1
                
                for entry in data.energy_plan.entries:
                    if entry.hour < now:
                        continue
                    # Score based on surplus energy and low price
                    surplus = entry.pv_forecast_wh - entry.load_forecast_wh
                    price_factor = 1 / (entry.price + 0.01) if entry.price else 1
                    score = (surplus / power_w + 1) * price_factor
                    
                    if score > best_score:
                        best_score = score
                        best_entry = entry
                
                if best_entry:
                    milestones.append(Milestone(
                        timestamp=best_entry.hour,
                        milestone_type="best_appliance_time",
                        title=f"Best time for {appliance_name}",
                        description=f"Optimal time to run {appliance_name} ({power_w:.0f}W) based on solar and prices",
                        priority=2,
                        data={"appliance": appliance_name, "power_w": power_w},
                    ))
        else:
            # Default recommendations for common appliances
            default_appliances = [
                ("Water heater", 2000),
                ("Washing machine", 1500),
                ("Dishwasher", 1200),
            ]
            for appliance_name, power_w in default_appliances:
                best_entry = None
                best_score = -1
                
                for entry in data.energy_plan.entries:
                    if entry.hour < now:
                        continue
                    surplus = entry.pv_forecast_wh - entry.load_forecast_wh
                    price_factor = 1 / (entry.price + 0.01) if entry.price else 1
                    score = (surplus / power_w + 1) * price_factor
                    
                    if score > best_score:
                        best_score = score
                        best_entry = entry
                
                if best_entry and best_score > 1:
                    milestones.append(Milestone(
                        timestamp=best_entry.hour,
                        milestone_type="best_appliance_time",
                        title=f"Best time for {appliance_name}",
                        description=f"Recommended time to run {appliance_name} based on solar surplus",
                        priority=1,
                        data={"appliance": appliance_name, "power_w": power_w},
                    ))
        
        # Find next cheap charging window
        charge_hours = data.energy_plan.get_next_charge_hours(3)
        if charge_hours:
            next_charge = charge_hours[0]
            milestones.append(Milestone(
                timestamp=next_charge.hour,
                milestone_type="cheap_charge_time",
                title="Cheap charging window",
                description=f"Battery charging planned at {next_charge.price:.3f}/kWh" if next_charge.price else "Battery charging planned",
                priority=4,
                data={"price": next_charge.price, "reason": next_charge.reason},
            ))
        
        # Find when battery will be full/low
        for entry in data.energy_plan.entries:
            if entry.hour > now:
                max_soc = float(self.entry.options.get("max_soc", 95))
                min_soc = float(self.entry.options.get("min_soc", 10))
                
                if entry.predicted_soc >= max_soc:
                    milestones.append(Milestone(
                        timestamp=entry.hour,
                        milestone_type="battery_full",
                        title="Battery will be full",
                        description=f"Expected to reach {entry.predicted_soc:.0f}% SOC",
                        priority=2,
                        data={"predicted_soc": entry.predicted_soc},
                    ))
                    break
        
        # Sort by priority (higher first) then by time
        milestones.sort(key=lambda m: (-m.priority, m.timestamp))
        
        # Return top 10 milestones
        return milestones[:10]
    
    async def async_add_away_period(
        self,
        start: datetime,
        end: datetime,
        label: str = "",
        reduce_load_percent: float = 50.0,
    ) -> str:
        """Add an away period and persist."""
        period_id = str(uuid.uuid4())[:8]
        period = AwayPeriod(
            id=period_id,
            start=start,
            end=end,
            label=label,
            reduce_load_percent=reduce_load_percent,
        )
        self._user_preferences.add_away_period(period)
        
        self._add_event(
            EventType.AWAY_MODE_STARTED if period.is_active() else EventType.MILESTONE_REACHED,
            EventSeverity.INFO,
            "Away period added",
            f"Away from {start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')}",
            {"period_id": period_id, "label": label},
        )
        
        await self._save_persisted_data()
        await self.async_refresh()
        return period_id
    
    async def async_remove_away_period(self, period_id: str) -> bool:
        """Remove an away period and persist."""
        removed = self._user_preferences.remove_away_period(period_id)
        if removed:
            await self._save_persisted_data()
            await self.async_refresh()
        return removed
    
    async def async_set_high_demand_appliance(self, name: str, power_w: float) -> None:
        """Add or update a high-demand appliance."""
        self._user_preferences.high_demand_appliances[name] = power_w
        await self._save_persisted_data()
        await self.async_refresh()
    
    async def async_remove_high_demand_appliance(self, name: str) -> bool:
        """Remove a high-demand appliance."""
        if name in self._user_preferences.high_demand_appliances:
            del self._user_preferences.high_demand_appliances[name]
            await self._save_persisted_data()
            await self.async_refresh()
            return True
        return False

    @property
    def device_type(self) -> SolaxDeviceType:
        """Get the configured Solax device type."""
        return SolaxDeviceType(
            self.entry.data.get(CONF_SOLAX_DEVICE_TYPE, SolaxDeviceType.MODBUS_REMOTE)
        )

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
            
            # Fetch weather data
            data.weather = await self._fetch_weather()
            
            # Fetch Solax state
            data.solax_state = await self._fetch_solax_state()
            
            # Update system health from Solax state
            await self._update_system_health(data)

            # Fetch generation forecast from forecast.solar API
            data.generation_forecast = await self._fetch_generation_forecast()

            # Mind plan: SolarMind.create_plan (updated twice per hour)
            data.plan_history = self._plan_history
            data.user_preferences = self._user_preferences
            now = datetime.now(timezone.utc)
            start_hour = now.replace(minute=0, second=0, microsecond=0)
            current_soc = data.solax_state.battery_soc or 50.0
            horizon = 48 if data.prices.tomorrow_available else 24
            data.plan_actions = create_plan_from_ha_data(
                dict(self.entry.options),
                data,
                start_hour,
                current_soc,
                horizon_hours=horizon,
            )
            
            # Determine active strategy
            data.active_strategy = await self._get_active_strategy()
            
            # Run strategy
            strategy_output = await self._run_strategy(data)
            data.strategy_output = strategy_output
            
            # Execute strategy output (apply to Solax)
            await self._execute_strategy(strategy_output)
            
            # Generate energy plan (considering user preferences)
            data.energy_plan = await self._generate_energy_plan(data)
            
            # Record actual values for historical tracking
            await self._record_actuals(data)
            
            # Detect and log events
            self._detect_events(data)
            
            # Calculate milestones
            data.milestones = self._calculate_milestones(data)
            
            # Attach persistent data
            data.plan_history = self._plan_history
            data.event_log = self._event_log
            data.user_preferences = self._user_preferences
            data.system_health = self._system_health
            
            # Store system config
            data.battery_capacity_wh = float(
                self.entry.options.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
            )
            data.max_pv_power_w = float(
                self.entry.options.get(CONF_MAX_PV_POWER, DEFAULT_MAX_PV_POWER)
            )
            
            data.last_error = None
            print("XXX", data)
            return data
            
        except Exception as err:
            _LOGGER.error("Error updating Solar Mind data: %s", err)
            # Return data with error but don't fail completely
            data = SolarMindData()
            data.last_update = datetime.now(timezone.utc)
            data.last_error = str(err)
            data.plan_history = self._plan_history
            data.event_log = self._event_log
            data.user_preferences = self._user_preferences
            data.system_health = self._system_health
            return data
    
    async def _update_system_health(self, data: SolarMindData) -> None:
        """Update system health metrics from Solax state."""
        # Try to get temperature sensors if available
        # These would be from the Solax integration's temperature sensors
        try:
            # Look for battery temperature sensor
            battery_temp_id = self.entry.data.get("battery_temperature")
            if battery_temp_id:
                state = self.hass.states.get(battery_temp_id)
                if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        self._system_health.battery_temperature = float(state.state)
                    except (ValueError, TypeError):
                        pass
            
            # Look for inverter temperature sensor
            inverter_temp_id = self.entry.data.get("inverter_temperature")
            if inverter_temp_id:
                state = self.hass.states.get(inverter_temp_id)
                if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        self._system_health.inverter_temperature = float(state.state)
                    except (ValueError, TypeError):
                        pass
            
            # Calculate 7-day forecast accuracy if we have enough history
            if len(self._plan_history.comparisons) >= 168:  # 7 days
                pv_errors = []
                for c in self._plan_history.comparisons[-168:]:
                    if c.predicted and c.actual and c.actual.pv_actual_wh is not None:
                        if c.predicted.pv_forecast_wh > 0:
                            error = abs(c.pv_error_wh or 0) / c.predicted.pv_forecast_wh
                            pv_errors.append(error)
                if pv_errors:
                    self._system_health.forecast_accuracy_7d = (1 - sum(pv_errors) / len(pv_errors)) * 100
            
            # Check for warnings
            if self._system_health.battery_temperature and self._system_health.battery_temperature > 45:
                self._system_health.add_warning("Battery temperature high (>45°C)")
            else:
                self._system_health.clear_warning("Battery temperature high (>45°C)")
            
            if self._system_health.inverter_temperature and self._system_health.inverter_temperature > 60:
                self._system_health.add_warning("Inverter temperature high (>60°C)")
            else:
                self._system_health.clear_warning("Inverter temperature high (>60°C)")
            
            if data.solax_state.battery_soc is not None:
                min_soc = float(self.entry.options.get("min_soc", 10))
                if data.solax_state.battery_soc <= min_soc:
                    self._system_health.add_warning(f"Battery at minimum SOC ({data.solax_state.battery_soc:.0f}%)")
                else:
                    self._system_health.clear_warning(f"Battery at minimum SOC ({data.solax_state.battery_soc:.0f}%)")
            
        except Exception as e:
            _LOGGER.debug("Error updating system health: %s", e)
    
    async def _generate_energy_plan(self, data: SolarMindData) -> EnergyPlan | None:
        """Generate energy plan based on current state, prices, and weather."""
        try:
            current_time = datetime.now(timezone.utc)
            current_soc = data.solax_state.battery_soc or 50.0
            
            # Update planner options in case they changed
            self._planner = EnergyPlanner(dict(self.entry.options))
            
            # Create the plan (pass plan history so load forecast uses historical data)
            plan = self._planner.create_plan(
                current_time=current_time,
                current_soc=current_soc,
                prices=data.prices,
                weather=data.weather,
                plan_history=self._plan_history,
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

            return StrategyOutput(
                status=SystemStatus.ERROR,
                mode=SOLAX_MODE_SELF_USE,
                reason=f"Strategy error: {e}",
            )

    async def _execute_strategy(self, output: StrategyOutput) -> None:
        """Execute strategy output by calling Solax entities."""

        
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
        """Manually trigger charge from grid using Battery Control mode."""
        output = StrategyOutput(
            status=SystemStatus.CHARGING,
            mode=SOLAX_MODE_BATTERY_CONTROL,
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
            mode=SOLAX_MODE_GRID_CONTROL,
            power_w=power,
            duration_seconds=duration_seconds,
            reason="Manual discharge to grid",
        )
        await self._execute_strategy(output)

    async def async_set_self_use(self) -> None:
        """Manually set self-use mode."""
        
        output = StrategyOutput(
            status=SystemStatus.SELF_USE,
            mode=SOLAX_MODE_SELF_USE,
            reason="Manual self-use mode",
        )
        await self._execute_strategy(output)

    async def async_set_house_from_grid(self) -> None:
        """Manually set house-from-grid mode (no discharge)."""
        
        output = StrategyOutput(
            status=SystemStatus.HOUSE_FROM_GRID,
            mode=SOLAX_MODE_NO_DISCHARGE,
            reason="Manual house from grid (no discharge)",
        )
        await self._execute_strategy(output)

    async def async_apply_strategy(self) -> None:
        """Manually trigger strategy evaluation and execution."""
        await self.async_refresh()
