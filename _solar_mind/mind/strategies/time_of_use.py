"""Time-of-use strategy - charge/discharge based on configured time windows."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ...const import (
    CONF_CHARGE_WINDOW_END,
    CONF_CHARGE_WINDOW_START,
    CONF_DISCHARGE_ALLOWED,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    DEFAULT_CHARGE_WINDOW_END,
    DEFAULT_CHARGE_WINDOW_START,
    DEFAULT_DISCHARGE_ALLOWED,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
    SOLAX_MODE_BATTERY_CONTROL,
    SOLAX_MODE_GRID_CONTROL,
    SOLAX_MODE_NO_DISCHARGE,
    SOLAX_MODE_SELF_USE,
    SystemStatus,
    CONF_AUTOREPEAT_DURATION,
    DEFAULT_AUTOREPEAT_DURATION,
)
from ..models import StrategyInput, StrategyOutput
from .base import BaseStrategy


class TimeOfUseStrategy(BaseStrategy):
    """Time-of-use strategy based on configured time windows.
    
    Charges the battery from the grid during the configured charge window
    (typically night hours with lower rates). Outside the window, uses
    self-use mode or prevents discharge based on configuration.
    """

    @property
    def key(self) -> str:
        """Return the unique strategy key."""
        return "time_of_use"

    @property
    def name(self) -> str:
        """Return the human-readable strategy name."""
        return "Time of use"

    @property
    def description(self) -> str:
        """Return a description of what this strategy does."""
        return (
            "Charge from grid during configured time window (e.g., night hours). "
            "Use battery for house during day. Ignores spot prices."
        )

    def _is_in_charge_window(
        self, current_hour: int, start_hour: int, end_hour: int
    ) -> bool:
        """Check if current hour is within the charge window.
        
        Handles windows that span midnight (e.g., 22:00 - 06:00).
        """
        if start_hour <= end_hour:
            # Simple case: window doesn't span midnight (e.g., 02:00 - 06:00)
            return start_hour <= current_hour < end_hour
        else:
            # Window spans midnight (e.g., 22:00 - 06:00)
            return current_hour >= start_hour or current_hour < end_hour

    def compute(
        self,
        input_data: StrategyInput,
        options: dict[str, Any],
    ) -> StrategyOutput:
        """Compute action based on time windows.
        
        During charge window: charge from grid
        Outside charge window: self-use or no-discharge based on config
        """
        current_hour = input_data.current_time.hour
        
        # Get options with defaults
        charge_start = int(options.get(CONF_CHARGE_WINDOW_START, DEFAULT_CHARGE_WINDOW_START))
        charge_end = int(options.get(CONF_CHARGE_WINDOW_END, DEFAULT_CHARGE_WINDOW_END))
        max_charge_power = int(options.get(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER))
        max_discharge_power = int(options.get(CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER))
        min_soc = float(options.get(CONF_MIN_SOC, DEFAULT_MIN_SOC))
        max_soc = float(options.get(CONF_MAX_SOC, DEFAULT_MAX_SOC))
        discharge_allowed = bool(options.get(CONF_DISCHARGE_ALLOWED, DEFAULT_DISCHARGE_ALLOWED))
        autorepeat_duration = int(options.get(CONF_AUTOREPEAT_DURATION, DEFAULT_AUTOREPEAT_DURATION))
        
        # Get current battery SOC
        current_soc = input_data.solax_state.battery_soc
        
        # Check if we're in the charge window
        in_charge_window = self._is_in_charge_window(
            current_hour, charge_start, charge_end
        )
        
        if in_charge_window:
            # During charge window - charge from grid if battery not full
            if current_soc is not None and current_soc >= max_soc:
                # Battery is full, just use self-use
                return StrategyOutput(
                    status=SystemStatus.SELF_USE,
                    mode=SOLAX_MODE_SELF_USE,
                    power_w=None,
                    duration_seconds=autorepeat_duration,
                    reason=f"Charge window but battery full ({current_soc:.0f}% >= {max_soc:.0f}%)",
                )
            
            return StrategyOutput(
                status=SystemStatus.CHARGING,
                mode=SOLAX_MODE_BATTERY_CONTROL,
                power_w=max_charge_power,
                duration_seconds=autorepeat_duration,
                reason=f"Charge window ({charge_start}:00-{charge_end}:00)",
            )
        
        # Outside charge window
        if discharge_allowed:
            # Allow battery discharge for house
            return StrategyOutput(
                status=SystemStatus.SELF_USE,
                mode=SOLAX_MODE_SELF_USE,
                power_w=None,
                duration_seconds=autorepeat_duration,
                reason="Outside charge window - self-use mode",
            )
        else:
            # Prevent battery discharge, house from grid
            return StrategyOutput(
                status=SystemStatus.HOUSE_FROM_GRID,
                mode=SOLAX_MODE_NO_DISCHARGE,
                power_w=None,
                duration_seconds=autorepeat_duration,
                reason="Outside charge window - no discharge (house from grid)",
            )

    def validate_options(self, options: dict[str, Any]) -> list[str]:
        """Validate time-of-use specific options."""
        errors = []
        
        charge_start = options.get(CONF_CHARGE_WINDOW_START)
        charge_end = options.get(CONF_CHARGE_WINDOW_END)
        
        if charge_start is not None and not (0 <= charge_start <= 23):
            errors.append("Charge window start must be between 0 and 23")
            
        if charge_end is not None and not (0 <= charge_end <= 23):
            errors.append("Charge window end must be between 0 and 23")
            
        return errors
