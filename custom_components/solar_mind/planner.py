"""Energy planner for Solar Mind - creates 24-48h energy plans."""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from .const import (
    CONF_AVERAGE_HOUSE_LOAD,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_EFFICIENCY,
    CONF_CHARGE_PRICE_THRESHOLD,
    CONF_CHARGE_WINDOW_END,
    CONF_CHARGE_WINDOW_START,
    CONF_DISCHARGE_ALLOWED,
    CONF_DISCHARGE_PRICE_THRESHOLD,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_PV_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    DEFAULT_AVERAGE_HOUSE_LOAD,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_EFFICIENCY,
    DEFAULT_CHARGE_PRICE_THRESHOLD,
    DEFAULT_CHARGE_WINDOW_END,
    DEFAULT_CHARGE_WINDOW_START,
    DEFAULT_DISCHARGE_ALLOWED,
    DEFAULT_DISCHARGE_PRICE_THRESHOLD,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_PV_POWER,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
)
from .models import (
    EnergyPlan,
    HourlyActual,
    HourlyPlanEntry,
    PlannedAction,
    PlanHistory,
    PredictionComparison,
    PriceData,
    SolaxState,
    WeatherForecast,
)

_LOGGER = logging.getLogger(__name__)


# House load patterns by hour (multiplier of average load)
# Based on typical residential patterns
LOAD_PATTERN_WEEKDAY = {
    0: 0.4, 1: 0.3, 2: 0.3, 3: 0.3, 4: 0.3, 5: 0.5,
    6: 0.8, 7: 1.2, 8: 1.0, 9: 0.7, 10: 0.6, 11: 0.6,
    12: 0.8, 13: 0.7, 14: 0.6, 15: 0.6, 16: 0.8, 17: 1.2,
    18: 1.5, 19: 1.4, 20: 1.3, 21: 1.1, 22: 0.8, 23: 0.5,
}

LOAD_PATTERN_WEEKEND = {
    0: 0.4, 1: 0.3, 2: 0.3, 3: 0.3, 4: 0.3, 5: 0.4,
    6: 0.5, 7: 0.7, 8: 0.9, 9: 1.0, 10: 1.1, 11: 1.1,
    12: 1.2, 13: 1.0, 14: 0.9, 15: 0.9, 16: 1.0, 17: 1.2,
    18: 1.4, 19: 1.3, 20: 1.2, 21: 1.0, 22: 0.8, 23: 0.5,
}


def _build_historical_load_profile(plan_history: PlanHistory) -> dict[tuple[int, int], float]:
    """
    Build average load (Wh) per (hour_of_day, weekday) from plan history actuals.
    Used as primary input for load forecasting when available.
    """
    slot_sums: dict[tuple[int, int], list[float]] = {}
    for comp in plan_history.comparisons:
        if not comp.actual or comp.actual.load_actual_wh is None:
            continue
        key = (comp.hour.hour, comp.hour.weekday())
        slot_sums.setdefault(key, []).append(comp.actual.load_actual_wh)
    return {
        key: sum(values) / len(values)
        for key, values in slot_sums.items()
        if values
    }


class EnergyPlanner:
    """Creates optimal energy plans based on prices, weather, and system state."""

    def __init__(self, options: dict[str, Any]) -> None:
        """Initialize the planner with configuration options."""
        self.battery_capacity = float(
            options.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
        )
        self.max_pv_power = float(
            options.get(CONF_MAX_PV_POWER, DEFAULT_MAX_PV_POWER)
        )
        self.average_load = float(
            options.get(CONF_AVERAGE_HOUSE_LOAD, DEFAULT_AVERAGE_HOUSE_LOAD)
        )
        self.battery_efficiency = float(
            options.get(CONF_BATTERY_EFFICIENCY, DEFAULT_BATTERY_EFFICIENCY)
        )
        self.min_soc = float(options.get(CONF_MIN_SOC, DEFAULT_MIN_SOC))
        self.max_soc = float(options.get(CONF_MAX_SOC, DEFAULT_MAX_SOC))
        self.max_charge_power = float(
            options.get(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER)
        )
        self.max_discharge_power = float(
            options.get(CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER)
        )
        self.charge_threshold = float(
            options.get(CONF_CHARGE_PRICE_THRESHOLD, DEFAULT_CHARGE_PRICE_THRESHOLD)
        )
        self.discharge_threshold = float(
            options.get(CONF_DISCHARGE_PRICE_THRESHOLD, DEFAULT_DISCHARGE_PRICE_THRESHOLD)
        )
        self.charge_window_start = int(
            options.get(CONF_CHARGE_WINDOW_START, DEFAULT_CHARGE_WINDOW_START)
        )
        self.charge_window_end = int(
            options.get(CONF_CHARGE_WINDOW_END, DEFAULT_CHARGE_WINDOW_END)
        )
        self.discharge_allowed = bool(
            options.get(CONF_DISCHARGE_ALLOWED, DEFAULT_DISCHARGE_ALLOWED)
        )

    def forecast_pv_generation(
        self,
        hour: datetime,
        weather: WeatherForecast,
    ) -> tuple[float, float, str]:
        """
        Forecast PV generation for a specific hour.
        
        Returns: (power_wh, solar_potential, condition)
        """
        hour_of_day = hour.hour
        
        # No generation outside daylight hours (simplified)
        if hour_of_day < 6 or hour_of_day > 20:
            return 0.0, 0.0, "night"
        
        # Calculate solar angle factor (simplified bell curve)
        # Peak at solar noon (around 12-13)
        solar_noon = 12.5
        hours_from_noon = abs(hour_of_day - solar_noon)
        # Cosine curve for solar angle
        angle_factor = max(0, math.cos(hours_from_noon * math.pi / 14))
        
        # Get weather condition
        solar_potential = 0.5
        condition = "unknown"
        
        for forecast in weather.hourly:
            forecast_dt = forecast.get("datetime")
            if forecast_dt and isinstance(forecast_dt, datetime):
                if forecast_dt.hour == hour_of_day:
                    condition = forecast.get("condition", "").lower()
                    # Map condition to solar potential
                    if condition in ("sunny", "clear", "clear-night"):
                        solar_potential = 1.0
                    elif condition in ("partlycloudy", "partly_cloudy"):
                        solar_potential = 0.65
                    elif condition in ("cloudy",):
                        solar_potential = 0.25
                    elif condition in ("rainy", "pouring", "lightning-rainy"):
                        solar_potential = 0.1
                    elif condition in ("snowy", "snowy-rainy"):
                        solar_potential = 0.15
                    elif condition in ("fog", "hail"):
                        solar_potential = 0.2
                    break
        
        # Calculate expected generation
        pv_power_w = self.max_pv_power * angle_factor * solar_potential
        pv_energy_wh = pv_power_w  # 1 hour = Wh
        
        return pv_energy_wh, solar_potential, condition

    def forecast_house_load(
        self,
        hour: datetime,
        historical_avg_wh: dict[tuple[int, int], float] | None = None,
    ) -> float:
        """
        Forecast house load for a specific hour.

        Prefer historical average load for the same (hour_of_day, weekday) when
        available; otherwise use configured average_load with weekday/weekend patterns.

        Returns: expected load in Wh
        """
        hour_of_day = hour.hour
        weekday = hour.weekday()
        key = (hour_of_day, weekday)

        if historical_avg_wh and key in historical_avg_wh:
            return historical_avg_wh[key]

        # Fallback: pattern-based estimate from configured average load
        if weekday < 5:  # Monday-Friday
            multiplier = LOAD_PATTERN_WEEKDAY.get(hour_of_day, 1.0)
        else:  # Saturday-Sunday
            multiplier = LOAD_PATTERN_WEEKEND.get(hour_of_day, 1.0)
        return self.average_load * multiplier  # 1 hour = Wh

    def _is_in_charge_window(self, hour: int) -> bool:
        """Check if hour is within the charge window."""
        if self.charge_window_start <= self.charge_window_end:
            return self.charge_window_start <= hour < self.charge_window_end
        else:
            # Window spans midnight
            return hour >= self.charge_window_start or hour < self.charge_window_end

    def _get_price_rank(self, price: float, all_prices: list[float]) -> int:
        """Get rank of price (1 = cheapest)."""
        sorted_prices = sorted(all_prices)
        for i, p in enumerate(sorted_prices):
            if price <= p:
                return i + 1
        return len(sorted_prices)

    def create_plan(
        self,
        current_time: datetime,
        current_soc: float,
        prices: PriceData,
        weather: WeatherForecast,
        plan_history: PlanHistory | None = None,
    ) -> EnergyPlan:
        """
        Create an optimal energy plan for the next 24-48 hours.

        The plan optimizes for:
        1. Minimize cost (charge when cheap, avoid buying when expensive)
        2. Maximize revenue (sell when expensive, if discharge allowed)
        3. Maximize self-consumption of solar

        When plan_history is provided, load forecasts use historical actual load
        per (hour_of_day, weekday) as primary source; otherwise pattern-based
        estimates are used.
        """
        plan = EnergyPlan(created_at=current_time)
        entries: list[HourlyPlanEntry] = []

        historical_avg_wh = (
            _build_historical_load_profile(plan_history) if plan_history else None
        )

        # Start from current hour
        start_hour = current_time.replace(minute=0, second=0, microsecond=0)

        # Determine plan horizon (24h if no tomorrow prices, 48h if available)
        horizon_hours = 48 if prices.tomorrow_available else 24

        # Collect all prices for ranking
        all_prices = [p.price for p in prices.today + prices.tomorrow]

        # Track battery state through the plan
        simulated_soc = current_soc if current_soc is not None else 50.0

        # First pass: calculate base forecasts
        hourly_data: list[dict[str, Any]] = []
        for i in range(horizon_hours):
            hour = start_hour + timedelta(hours=i)

            pv_wh, solar_potential, condition = self.forecast_pv_generation(
                hour, weather
            )
            load_wh = self.forecast_house_load(hour, historical_avg_wh)
            price = prices.get_price_at(hour)
            
            hourly_data.append({
                "hour": hour,
                "pv_wh": pv_wh,
                "load_wh": load_wh,
                "price": price,
                "solar_potential": solar_potential,
                "condition": condition,
            })
        
        # Second pass: determine optimal actions
        for i, data in enumerate(hourly_data):
            hour = data["hour"]
            pv_wh = data["pv_wh"]
            load_wh = data["load_wh"]
            price = data["price"]
            solar_potential = data["solar_potential"]
            condition = data["condition"]
            
            hour_of_day = hour.hour
            in_charge_window = self._is_in_charge_window(hour_of_day)
            
            # Calculate net energy balance (PV - Load)
            net_energy = pv_wh - load_wh
            
            # Initialize values
            action = PlannedAction.SELF_USE
            grid_import = 0.0
            grid_export = 0.0
            battery_charge = 0.0
            battery_discharge = 0.0
            reason = ""
            
            # Price analysis
            price_is_cheap = price is not None and price <= self.charge_threshold
            price_is_expensive = price is not None and price >= self.discharge_threshold
            price_rank = self._get_price_rank(price, all_prices) if price else 12
            
            # Calculate battery capacity limits
            min_soc_wh = self.battery_capacity * (self.min_soc / 100)
            max_soc_wh = self.battery_capacity * (self.max_soc / 100)
            current_battery_wh = self.battery_capacity * (simulated_soc / 100)
            available_charge_wh = max_soc_wh - current_battery_wh
            available_discharge_wh = current_battery_wh - min_soc_wh
            
            # Decision logic
            if price_is_cheap and in_charge_window and available_charge_wh > 0:
                # Charge from grid - cheap price in charge window
                action = PlannedAction.CHARGE
                charge_power = min(self.max_charge_power, available_charge_wh)
                battery_charge = charge_power * self.battery_efficiency
                grid_import = load_wh + charge_power - max(0, pv_wh)
                if pv_wh > load_wh:
                    # PV covers load + some charging
                    battery_charge = min(battery_charge + (pv_wh - load_wh), available_charge_wh)
                    grid_import = max(0, charge_power - (pv_wh - load_wh))
                reason = f"Cheap price ({price:.3f}) in charge window, rank #{price_rank}"
                
            elif price_is_expensive and self.discharge_allowed and available_discharge_wh > 0:
                # Discharge to grid - expensive price
                action = PlannedAction.DISCHARGE
                discharge_power = min(self.max_discharge_power, available_discharge_wh)
                battery_discharge = discharge_power
                grid_export = (pv_wh + discharge_power * self.battery_efficiency) - load_wh
                grid_export = max(0, grid_export)
                reason = f"Expensive price ({price:.3f}), selling to grid"
                
            elif net_energy > 0:
                # PV surplus - charge battery or export
                action = PlannedAction.SELF_USE
                if available_charge_wh > 0:
                    battery_charge = min(net_energy * self.battery_efficiency, available_charge_wh)
                    remaining_surplus = net_energy - battery_charge / self.battery_efficiency
                    grid_export = max(0, remaining_surplus)
                else:
                    grid_export = net_energy
                reason = "PV surplus - storing/exporting"
                
            elif available_discharge_wh > 0:
                # PV deficit but battery available
                action = PlannedAction.SELF_USE
                needed = -net_energy  # How much we need
                battery_discharge = min(needed / self.battery_efficiency, available_discharge_wh)
                remaining_deficit = needed - battery_discharge * self.battery_efficiency
                grid_import = max(0, remaining_deficit)
                reason = f"Using battery (SOC: {simulated_soc:.0f}%)"
                
            else:
                # PV deficit and battery low - use grid
                action = PlannedAction.IDLE
                grid_import = -net_energy
                reason = f"Battery low ({simulated_soc:.0f}%), using grid"
            
            # Update simulated SOC
            soc_change = (battery_charge - battery_discharge) / self.battery_capacity * 100
            simulated_soc = max(self.min_soc, min(self.max_soc, simulated_soc + soc_change))
            
            entry = HourlyPlanEntry(
                hour=hour,
                action=action,
                pv_forecast_wh=pv_wh,
                load_forecast_wh=load_wh,
                price=price,
                planned_grid_import_wh=max(0, grid_import),
                planned_grid_export_wh=max(0, grid_export),
                planned_battery_charge_wh=battery_charge,
                planned_battery_discharge_wh=battery_discharge,
                predicted_soc=simulated_soc,
                solar_potential=solar_potential,
                weather_condition=condition,
                reason=reason,
            )
            entries.append(entry)
        
        # Calculate totals
        plan.entries = entries
        plan.total_pv_forecast_wh = sum(e.pv_forecast_wh for e in entries)
        plan.total_load_forecast_wh = sum(e.load_forecast_wh for e in entries)
        plan.total_grid_import_wh = sum(e.planned_grid_import_wh for e in entries)
        plan.total_grid_export_wh = sum(e.planned_grid_export_wh for e in entries)
        
        # Estimate cost/revenue
        for entry in entries:
            if entry.price:
                plan.estimated_cost += entry.planned_grid_import_wh * entry.price / 1000
                plan.estimated_revenue += entry.planned_grid_export_wh * entry.price / 1000
        
        _LOGGER.debug(
            "Created energy plan: %d hours, PV: %.1f kWh, Load: %.1f kWh, "
            "Import: %.1f kWh, Export: %.1f kWh",
            len(entries),
            plan.total_pv_forecast_wh / 1000,
            plan.total_load_forecast_wh / 1000,
            plan.total_grid_import_wh / 1000,
            plan.total_grid_export_wh / 1000,
        )
        
        return plan


def record_actual_hour(
    plan_history: PlanHistory,
    energy_plan: EnergyPlan | None,
    hour: datetime,
    solax_state: SolaxState,
    price: float | None,
    pv_power_avg: float | None = None,
    house_load_avg: float | None = None,
) -> None:
    """
    Record actual values for an hour and compare with prediction.
    
    This should be called at the end of each hour to track accuracy.
    """
    # Get the prediction for this hour
    predicted: HourlyPlanEntry | None = None
    if energy_plan:
        predicted = energy_plan.get_entry_at(hour)
    
    # Determine action that was taken
    action_taken: PlannedAction | None = None
    if solax_state.current_mode:
        mode = solax_state.current_mode.lower()
        if "grid" in mode and solax_state.active_power and solax_state.active_power > 0:
            action_taken = PlannedAction.CHARGE
        elif "battery" in mode or (solax_state.active_power and solax_state.active_power < 0):
            action_taken = PlannedAction.DISCHARGE
        elif "self" in mode:
            action_taken = PlannedAction.SELF_USE
        else:
            action_taken = PlannedAction.IDLE
    
    # Create actual record
    actual = HourlyActual(
        hour=hour,
        action_taken=action_taken,
        pv_actual_wh=pv_power_avg if pv_power_avg is not None else None,
        load_actual_wh=house_load_avg if house_load_avg is not None else None,
        grid_import_actual_wh=solax_state.grid_import,
        grid_export_actual_wh=solax_state.grid_export,
        battery_soc_end=solax_state.battery_soc,
        price_actual=price,
    )
    
    # Add comparison
    comparison = PredictionComparison(
        hour=hour,
        predicted=predicted,
        actual=actual,
    )
    plan_history.add_comparison(comparison)
    
    if predicted:
        _LOGGER.debug(
            "Hour %s: Predicted PV=%.1f Wh, Actual=%.1f Wh, Error=%.1f Wh",
            hour.strftime("%H:%M"),
            predicted.pv_forecast_wh,
            actual.pv_actual_wh or 0,
            comparison.pv_error_wh or 0,
        )
