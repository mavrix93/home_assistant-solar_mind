"""Manual strategy - no automatic decisions."""
from __future__ import annotations

from typing import Any

from ..const import SOLAX_MODE_DISABLED, SystemStatus
from ..models import StrategyInput, StrategyOutput
from .base import BaseStrategy


class ManualStrategy(BaseStrategy):
    """Manual strategy that makes no automatic decisions.
    
    In this mode, the integration will not automatically control
    the inverter. Users must use services to manually control
    charge/discharge behavior.
    """

    @property
    def key(self) -> str:
        """Return the unique strategy key."""
        return "manual"

    @property
    def name(self) -> str:
        """Return the human-readable strategy name."""
        return "Manual"

    @property
    def description(self) -> str:
        """Return a description of what this strategy does."""
        return (
            "No automatic decisions. Use services to manually control "
            "the inverter behavior."
        )

    def compute(
        self,
        input_data: StrategyInput,
        options: dict[str, Any],
    ) -> StrategyOutput:
        """Return idle status - no automatic action.
        
        In manual mode, we don't change anything automatically.
        The mode stays as IDLE and no commands are sent to the inverter.
        """
        return StrategyOutput(
            status=SystemStatus.IDLE,
            mode=SOLAX_MODE_DISABLED,
            power_w=None,
            duration_seconds=None,
            reason="Manual mode - no automatic control",
        )
