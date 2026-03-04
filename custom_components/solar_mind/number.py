"""Number platform for Solar Mind integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, PERCENTAGE, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.solar_mind.ha.const import DOMAIN

from .ha.coordinator import SolarMindCoordinator


@dataclass(frozen=True, kw_only=True)
class SolarMindNumberEntityDescription(NumberEntityDescription):
    """Describes a Solar Mind number entity."""

    value_fn: Callable[[SolarMindCoordinator], float | None]
    set_value_fn: Callable[[SolarMindCoordinator, float], Any]


NUMBER_DESCRIPTIONS: tuple[SolarMindNumberEntityDescription, ...] = (
    SolarMindNumberEntityDescription(
        key="target_battery_soc",
        name="Target Battery SOC",
        icon="mdi:battery-charging-high",
        native_min_value=10,
        native_max_value=100,
        native_step=5,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        value_fn=lambda coord: float(coord.target_soc),
        set_value_fn=lambda coord, val: setattr(coord, "target_soc", int(val)),
    ),
    SolarMindNumberEntityDescription(
        key="charge_to_soc_power",
        name="Charge to SOC Power",
        icon="mdi:flash",
        native_min_value=100,
        native_max_value=15000,
        native_step=100,
        native_unit_of_measurement=UnitOfPower.WATT,
        mode=NumberMode.BOX,
        value_fn=lambda coord: float(coord.charge_to_soc_power_w),
        set_value_fn=lambda coord, val: setattr(coord, "charge_to_soc_power_w", int(val)),
    ),
    SolarMindNumberEntityDescription(
        key="charge_to_soc_duration",
        name="Charge to SOC Duration",
        icon="mdi:timer-outline",
        native_min_value=300,
        native_max_value=86400,
        native_step=300,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        mode=NumberMode.SLIDER,
        value_fn=lambda coord: float(coord.charge_to_soc_duration_s),
        set_value_fn=lambda coord, val: setattr(coord, "charge_to_soc_duration_s", int(val)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Mind number entities from a config entry."""
    coordinator: SolarMindCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        SolarMindNumber(coordinator, entry, description)
        for description in NUMBER_DESCRIPTIONS
    )


class SolarMindNumber(CoordinatorEntity[SolarMindCoordinator], NumberEntity):
    """Representation of a Solar Mind number entity."""

    entity_description: SolarMindNumberEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SolarMindCoordinator,
        entry: ConfigEntry,
        description: SolarMindNumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry

        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Solar Mind"),
            manufacturer="Solar Mind",
            model="Energy Optimizer",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        self.entity_description.set_value_fn(self.coordinator, value)
        self.async_write_ha_state()
