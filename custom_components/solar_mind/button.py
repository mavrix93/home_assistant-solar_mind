"""Button platform for Solar Mind integration."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.solar_mind.ha.const import DOMAIN

from .ha.coordinator import SolarMindCoordinator


@dataclass(frozen=True, kw_only=True)
class SolarMindButtonEntityDescription(ButtonEntityDescription):
    """Describes a Solar Mind button entity."""

    press_fn: Callable[[SolarMindCoordinator], Coroutine[Any, Any, None]]


BUTTON_DESCRIPTIONS: tuple[SolarMindButtonEntityDescription, ...] = (
    SolarMindButtonEntityDescription(
        key="charge_battery_from_grid",
        name="Charge Battery from Grid",
        icon="mdi:battery-charging",
        press_fn=lambda coord: coord.async_charge_from_grid(),
    ),
    SolarMindButtonEntityDescription(
        key="discharge_battery_to_grid",
        name="Discharge Battery to Grid",
        icon="mdi:battery-arrow-down",
        press_fn=lambda coord: coord.async_discharge_to_grid(),
    ),
    SolarMindButtonEntityDescription(
        key="set_self_use",
        name="Set Self Use Mode",
        icon="mdi:home-battery",
        press_fn=lambda coord: coord.async_set_self_use(),
    ),
    SolarMindButtonEntityDescription(
        key="set_house_use_grid",
        name="Set House Use Grid",
        icon="mdi:transmission-tower",
        press_fn=lambda coord: coord.async_set_house_from_grid(),
    ),
    SolarMindButtonEntityDescription(
        key="set_battery_for_house",
        name="Set Battery for House",
        icon="mdi:home-lightning-bolt",
        press_fn=lambda coord: coord.async_set_self_use(),
    ),
    SolarMindButtonEntityDescription(
        key="apply_strategy",
        name="Apply Strategy",
        icon="mdi:strategy",
        press_fn=lambda coord: coord.async_apply_strategy(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Mind buttons from a config entry."""
    coordinator: SolarMindCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        SolarMindButton(coordinator, entry, description)
        for description in BUTTON_DESCRIPTIONS
    )


class SolarMindButton(CoordinatorEntity[SolarMindCoordinator], ButtonEntity):
    """Representation of a Solar Mind button."""

    entity_description: SolarMindButtonEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SolarMindCoordinator,
        entry: ConfigEntry,
        description: SolarMindButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
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

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.entity_description.press_fn(self.coordinator)
