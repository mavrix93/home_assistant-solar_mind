"""Strategy registry for Solar Mind."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseStrategy
from .manual import ManualStrategy
from .self_use_only import SelfUseOnlyStrategy
from .spot_price import SpotPriceWeatherStrategy
from .time_of_use import TimeOfUseStrategy

if TYPE_CHECKING:
    from ...const import StrategyKey

# Strategy registry: maps strategy key to strategy class
STRATEGIES: dict[str, type[BaseStrategy]] = {
    "spot_price_weather": SpotPriceWeatherStrategy,
    "time_of_use": TimeOfUseStrategy,
    "self_use_only": SelfUseOnlyStrategy,
    "manual": ManualStrategy,
}


def get_strategy(key: str) -> BaseStrategy:
    """Get a strategy instance by key.
    
    Args:
        key: Strategy identifier (e.g., "spot_price_weather")
        
    Returns:
        Strategy instance
        
    Raises:
        ValueError: If strategy key is not found
    """
    strategy_class = STRATEGIES.get(key)
    if strategy_class is None:
        raise ValueError(f"Unknown strategy: {key}")
    return strategy_class()


def get_available_strategies() -> list[str]:
    """Get list of available strategy keys."""
    return list(STRATEGIES.keys())


__all__ = [
    "BaseStrategy",
    "ManualStrategy",
    "SelfUseOnlyStrategy",
    "SpotPriceWeatherStrategy",
    "TimeOfUseStrategy",
    "STRATEGIES",
    "get_strategy",
    "get_available_strategies",
]
