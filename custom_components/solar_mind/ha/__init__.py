"""Home Assistant integration for Solar Mind – data gathering and plan entity."""

from .plan_adapter import create_plan_from_ha_data

# Coordinator lives at root for HA platform discovery; re-export for clarity
from ..coordinator import SolarMindCoordinator

__all__ = ["SolarMindCoordinator", "create_plan_from_ha_data"]
