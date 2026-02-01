"""Base strategy interface for Solar Mind."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import StrategyInput, StrategyOutput


class BaseStrategy(ABC):
    """Abstract base class for all strategies.
    
    Each strategy must implement the compute method which takes
    input data (prices, weather, current state) and returns
    the recommended action.
    """

    @property
    @abstractmethod
    def key(self) -> str:
        """Return the unique strategy key."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the human-readable strategy name."""
        ...

    @property
    def description(self) -> str:
        """Return a description of what this strategy does."""
        return ""

    @abstractmethod
    def compute(
        self,
        input_data: StrategyInput,
        options: dict[str, Any],
    ) -> StrategyOutput:
        """Compute the recommended action based on input data.
        
        Args:
            input_data: Current state including prices, weather, and Solax state
            options: User-configured options (thresholds, windows, etc.)
            
        Returns:
            StrategyOutput with recommended mode, power, and reason
        """
        ...

    def validate_options(self, options: dict[str, Any]) -> list[str]:
        """Validate options for this strategy.
        
        Args:
            options: User-configured options
            
        Returns:
            List of validation error messages (empty if valid)
        """
        return []
