"""Self-use only strategy - inverter handles everything automatically."""
from __future__ import annotations

from typing import Any

from ..const import SOLAX_MODE_SELF_USE, SystemStatus
from ..models import StrategyInput, StrategyOutput
from .base import BaseStrategy


class SelfUseOnlyStrategy(BaseStrategy):
    """Self-use only strategy.
    
    In this mode, the inverter is set to self-use mode where it
    automatically manages battery charging from PV and discharging
    to cover house load. No grid charging or selling is performed.
    """

    @property
    def key(self) -> str:
        """Return the unique strategy key."""
        return "self_use_only"

    @property
    def name(self) -> str:
        """Return the human-readable strategy name."""
        return "Self use only"

    @property
    def description(self) -> str:
        """Return a description of what this strategy does."""
        return (
            "Inverter self-use mode. Battery charges from PV and "
            "discharges to cover house load. No grid charging or selling."
        )

    def compute(
        self,
        input_data: StrategyInput,
        options: dict[str, Any],
    ) -> StrategyOutput:
        """Return self-use mode.
        
        Simply sets the inverter to self-use mode where it handles
        everything automatically.
        """
        return StrategyOutput(
            status=SystemStatus.SELF_USE,
            mode=SOLAX_MODE_SELF_USE,
            power_w=None,
            duration_seconds=None,
            reason="Self-use mode - inverter manages battery automatically",
        )
