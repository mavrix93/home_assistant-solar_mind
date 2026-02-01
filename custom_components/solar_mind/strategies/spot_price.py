"""Spot price + weather strategy - the primary optimization strategy."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..const import (
    CONF_AUTOREPEAT_DURATION,
    CONF_CHARGE_PRICE_THRESHOLD,
    CONF_CHARGE_WINDOW_END,
    CONF_CHARGE_WINDOW_START,
    CONF_DISCHARGE_ALLOWED,
    CONF_DISCHARGE_PRICE_THRESHOLD,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    DEFAULT_AUTOREPEAT_DURATION,
    DEFAULT_CHARGE_PRICE_THRESHOLD,
    DEFAULT_CHARGE_WINDOW_END,
    DEFAULT_CHARGE_WINDOW_START,
    DEFAULT_DISCHARGE_ALLOWED,
    DEFAULT_DISCHARGE_PRICE_THRESHOLD,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
    SOLAX_MODE_BATTERY_CONTROL,
    SOLAX_MODE_GRID_CONTROL,
    SOLAX_MODE_NO_DISCHARGE,
    SOLAX_MODE_SELF_USE,
    SystemStatus,
)
from ..models import PriceData, StrategyInput, StrategyOutput, WeatherForecast
from .base import BaseStrategy


class SpotPriceWeatherStrategy(BaseStrategy):
    """Spot price + weather optimization strategy.
    
    This is the primary strategy that optimizes battery usage based on:
    - Current and forecasted spot electricity prices
    - Weather forecast (solar production potential)
    - Battery state of charge
    - Configured thresholds and windows
    
    Decision logic:
    1. If price < charge_threshold and in charge window and SOC < max_soc:
       → Charge from grid
    2. If price > discharge_threshold and discharge allowed and SOC > min_soc:
       → Discharge to grid (sell)
    3. If good solar forecast and SOC > min_soc:
       → Self use (battery for house)
    4. Otherwise:
       → House from grid (no discharge)
    """

    @property
    def key(self) -> str:
        """Return the unique strategy key."""
        return "spot_price_weather"

    @property
    def name(self) -> str:
        """Return the human-readable strategy name."""
        return "Spot price + weather"

    @property
    def description(self) -> str:
        """Return a description of what this strategy does."""
        return (
            "Optimizes battery usage based on spot prices and weather forecast. "
            "Charges when prices are low, uses battery when prices are high or "
            "solar production is good."
        )

    def _is_in_charge_window(
        self, current_hour: int, start_hour: int, end_hour: int
    ) -> bool:
        """Check if current hour is within the charge window."""
        if start_hour <= end_hour:
            return start_hour <= current_hour < end_hour
        else:
            # Window spans midnight
            return current_hour >= start_hour or current_hour < end_hour

    def _get_price_percentile(self, prices: PriceData, current_price: float) -> int:
        """Get the percentile rank of current price (1 = cheapest, 24 = most expensive)."""
        all_prices = sorted([p.price for p in prices.today + prices.tomorrow])
        if not all_prices:
            return 12  # Middle if no data
        
        rank = 1
        for price in all_prices:
            if current_price > price:
                rank += 1
        return rank

    def _is_price_cheap(
        self, prices: PriceData, current_price: float, threshold: float
    ) -> bool:
        """Check if current price is considered cheap."""
        return current_price <= threshold

    def _is_price_expensive(
        self, prices: PriceData, current_price: float, threshold: float
    ) -> bool:
        """Check if current price is considered expensive."""
        return current_price >= threshold

    def _has_good_solar_forecast(
        self, weather: WeatherForecast, current_hour: int
    ) -> bool:
        """Check if solar forecast is good for the current hour."""
        # Only consider solar during daylight hours (6-20)
        if not (6 <= current_hour <= 20):
            return False
        
        solar_potential = weather.get_solar_potential(current_hour)
        return solar_potential >= 0.5  # At least 50% solar potential

    def compute(
        self,
        input_data: StrategyInput,
        options: dict[str, Any],
    ) -> StrategyOutput:
        """Compute optimal action based on prices, weather, and state."""
        current_hour = input_data.current_time.hour
        prices = input_data.prices
        weather = input_data.weather
        solax_state = input_data.solax_state
        
        # Get options with defaults
        charge_threshold = float(
            options.get(CONF_CHARGE_PRICE_THRESHOLD, DEFAULT_CHARGE_PRICE_THRESHOLD)
        )
        discharge_threshold = float(
            options.get(CONF_DISCHARGE_PRICE_THRESHOLD, DEFAULT_DISCHARGE_PRICE_THRESHOLD)
        )
        charge_start = int(
            options.get(CONF_CHARGE_WINDOW_START, DEFAULT_CHARGE_WINDOW_START)
        )
        charge_end = int(
            options.get(CONF_CHARGE_WINDOW_END, DEFAULT_CHARGE_WINDOW_END)
        )
        max_charge_power = int(
            options.get(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER)
        )
        max_discharge_power = int(
            options.get(CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER)
        )
        min_soc = float(options.get(CONF_MIN_SOC, DEFAULT_MIN_SOC))
        max_soc = float(options.get(CONF_MAX_SOC, DEFAULT_MAX_SOC))
        discharge_allowed = bool(
            options.get(CONF_DISCHARGE_ALLOWED, DEFAULT_DISCHARGE_ALLOWED)
        )
        autorepeat_duration = int(
            options.get(CONF_AUTOREPEAT_DURATION, DEFAULT_AUTOREPEAT_DURATION)
        )
        
        # Get current state
        current_soc = solax_state.battery_soc
        current_price = prices.current_price
        
        # If we don't have price data, fall back to time-of-use logic
        if current_price is None:
            return self._fallback_time_of_use(
                current_hour, charge_start, charge_end, 
                max_charge_power, autorepeat_duration, current_soc, max_soc
            )
        
        in_charge_window = self._is_in_charge_window(
            current_hour, charge_start, charge_end
        )
        price_is_cheap = self._is_price_cheap(prices, current_price, charge_threshold)
        price_is_expensive = self._is_price_expensive(
            prices, current_price, discharge_threshold
        )
        good_solar = self._has_good_solar_forecast(weather, current_hour)
        
        # Decision 1: Charge from grid when price is cheap
        if price_is_cheap and in_charge_window:
            if current_soc is not None and current_soc >= max_soc:
                return StrategyOutput(
                    status=SystemStatus.SELF_USE,
                    mode=SOLAX_MODE_SELF_USE,
                    power_w=None,
                    duration_seconds=autorepeat_duration,
                    reason=f"Cheap price ({current_price:.3f}) but battery full ({current_soc:.0f}%)",
                )
            
            return StrategyOutput(
                status=SystemStatus.CHARGING,
                mode=SOLAX_MODE_GRID_CONTROL,
                power_w=max_charge_power,
                duration_seconds=autorepeat_duration,
                reason=f"Cheap price ({current_price:.3f} <= {charge_threshold:.3f}) in charge window",
            )
        
        # Decision 2: Discharge to grid when price is expensive (if allowed)
        if price_is_expensive and discharge_allowed:
            if current_soc is not None and current_soc <= min_soc:
                return StrategyOutput(
                    status=SystemStatus.HOUSE_FROM_GRID,
                    mode=SOLAX_MODE_NO_DISCHARGE,
                    power_w=None,
                    duration_seconds=autorepeat_duration,
                    reason=f"Expensive price but battery low ({current_soc:.0f}% <= {min_soc:.0f}%)",
                )
            
            return StrategyOutput(
                status=SystemStatus.DISCHARGING,
                mode=SOLAX_MODE_BATTERY_CONTROL,
                power_w=-max_discharge_power,  # Negative = discharge
                duration_seconds=autorepeat_duration,
                reason=f"Expensive price ({current_price:.3f} >= {discharge_threshold:.3f}) - selling to grid",
            )
        
        # Decision 3: Self-use when solar is good or we have battery capacity
        if good_solar or (current_soc is not None and current_soc > min_soc):
            return StrategyOutput(
                status=SystemStatus.SELF_USE,
                mode=SOLAX_MODE_SELF_USE,
                power_w=None,
                duration_seconds=autorepeat_duration,
                reason="Good solar forecast" if good_solar else f"Battery available ({current_soc:.0f}%)",
            )
        
        # Decision 4: House from grid (preserve battery)
        return StrategyOutput(
            status=SystemStatus.HOUSE_FROM_GRID,
            mode=SOLAX_MODE_NO_DISCHARGE,
            power_w=None,
            duration_seconds=autorepeat_duration,
            reason=f"Preserving battery (SOC: {current_soc:.0f}%)" if current_soc else "Preserving battery",
        )

    def _fallback_time_of_use(
        self,
        current_hour: int,
        charge_start: int,
        charge_end: int,
        max_charge_power: int,
        autorepeat_duration: int,
        current_soc: float | None,
        max_soc: float,
    ) -> StrategyOutput:
        """Fallback to time-of-use logic when price data is unavailable."""
        in_charge_window = self._is_in_charge_window(
            current_hour, charge_start, charge_end
        )
        
        if in_charge_window:
            if current_soc is not None and current_soc >= max_soc:
                return StrategyOutput(
                    status=SystemStatus.SELF_USE,
                    mode=SOLAX_MODE_SELF_USE,
                    power_w=None,
                    duration_seconds=autorepeat_duration,
                    reason="No price data, charge window, battery full",
                )
            
            return StrategyOutput(
                status=SystemStatus.CHARGING,
                mode=SOLAX_MODE_GRID_CONTROL,
                power_w=max_charge_power,
                duration_seconds=autorepeat_duration,
                reason=f"No price data - using charge window ({charge_start}:00-{charge_end}:00)",
            )
        
        return StrategyOutput(
            status=SystemStatus.SELF_USE,
            mode=SOLAX_MODE_SELF_USE,
            power_w=None,
            duration_seconds=autorepeat_duration,
            reason="No price data - self-use mode",
        )

    def validate_options(self, options: dict[str, Any]) -> list[str]:
        """Validate spot price strategy options."""
        errors = []
        
        charge_threshold = options.get(CONF_CHARGE_PRICE_THRESHOLD)
        discharge_threshold = options.get(CONF_DISCHARGE_PRICE_THRESHOLD)
        
        if charge_threshold is not None and discharge_threshold is not None:
            if charge_threshold >= discharge_threshold:
                errors.append(
                    "Charge threshold should be lower than discharge threshold"
                )
        
        min_soc = options.get(CONF_MIN_SOC)
        max_soc = options.get(CONF_MAX_SOC)
        
        if min_soc is not None and max_soc is not None:
            if min_soc >= max_soc:
                errors.append("Minimum SOC should be lower than maximum SOC")
        
        return errors
