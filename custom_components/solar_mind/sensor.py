"""Sensor platform for Solar Mind integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, STRATEGY_DISPLAY_NAMES, SystemStatus
from .coordinator import SolarMindCoordinator
from .models import SolarMindData


@dataclass(frozen=True, kw_only=True)
class SolarMindSensorEntityDescription(SensorEntityDescription):
    """Describes a Solar Mind sensor entity."""

    value_fn: Callable[[SolarMindData], Any]
    attr_fn: Callable[[SolarMindData], dict[str, Any]] | None = None


def _get_status(data: SolarMindData) -> str:
    """Get current status."""
    if data.strategy_output:
        return data.strategy_output.status.value
    return SystemStatus.IDLE.value


def _get_recommended_action(data: SolarMindData) -> str:
    """Get recommended action."""
    if data.strategy_output:
        return data.strategy_output.recommended_action
    return "No recommendation"


def _get_current_price(data: SolarMindData) -> float | None:
    """Get current spot price."""
    return data.prices.current_price


def _get_active_strategy(data: SolarMindData) -> str:
    """Get active strategy display name."""
    return STRATEGY_DISPLAY_NAMES.get(data.active_strategy, data.active_strategy.value)


def _get_strategy_mode(data: SolarMindData) -> str:
    """Get current strategy mode/decision."""
    if data.strategy_output:
        power_str = f"_{data.strategy_output.power_w}w" if data.strategy_output.power_w else ""
        return f"{data.strategy_output.status.value}{power_str}"
    return "idle"


def _get_last_update(data: SolarMindData) -> datetime | None:
    """Get last update time."""
    return data.last_update


def _get_last_error(data: SolarMindData) -> str | None:
    """Get last error message."""
    return data.last_error


def _get_next_cheap_hour(data: SolarMindData) -> str | None:
    """Get next cheap hour."""
    if not data.prices.today and not data.prices.tomorrow:
        return None
    
    now = datetime.now()
    cheap_hours = data.prices.get_cheapest_hours(6)
    
    # Find next cheap hour that's in the future
    for hp in cheap_hours:
        if hp.start > now:
            return hp.start.strftime("%H:%M")
    
    return None


def _get_next_cheap_hour_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get next cheap hour attributes."""
    if not data.prices.today and not data.prices.tomorrow:
        return {}
    
    now = datetime.now()
    cheap_hours = data.prices.get_cheapest_hours(6)
    
    attrs: dict[str, Any] = {"cheap_hours": []}
    
    for hp in cheap_hours:
        attrs["cheap_hours"].append({
            "time": hp.start.strftime("%H:%M"),
            "price": hp.price,
            "is_future": hp.start > now,
        })
        
        if hp.start > now and "next_start" not in attrs:
            attrs["next_start"] = hp.start.isoformat()
            attrs["next_price"] = hp.price
    
    return attrs


def _get_cheapest_hours_today(data: SolarMindData) -> str:
    """Get list of cheapest hours today."""
    if not data.prices.today:
        return "No data"
    
    # Sort today's prices and get cheapest 6
    sorted_today = sorted(data.prices.today, key=lambda x: x.price)[:6]
    sorted_by_time = sorted(sorted_today, key=lambda x: x.start.hour)
    
    hours = [str(hp.start.hour) for hp in sorted_by_time]
    return ", ".join(hours) if hours else "No data"


def _get_cheapest_hours_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get cheapest hours attributes."""
    if not data.prices.today:
        return {}
    
    sorted_today = sorted(data.prices.today, key=lambda x: x.price)[:6]
    
    return {
        "hours": [
            {"hour": hp.start.hour, "price": hp.price}
            for hp in sorted(sorted_today, key=lambda x: x.start.hour)
        ]
    }


def _get_next_action(data: SolarMindData) -> str | None:
    """Get next planned action."""
    if data.strategy_output:
        return data.strategy_output.reason
    return None


def _get_battery_soc(data: SolarMindData) -> float | None:
    """Get battery SOC from last read."""
    return data.solax_state.battery_soc


def _get_status_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get status attributes."""
    attrs: dict[str, Any] = {}
    
    if data.strategy_output:
        attrs["mode"] = data.strategy_output.mode
        attrs["reason"] = data.strategy_output.reason
        if data.strategy_output.power_w is not None:
            attrs["power_w"] = data.strategy_output.power_w
        if data.strategy_output.duration_seconds is not None:
            attrs["duration_seconds"] = data.strategy_output.duration_seconds
    
    if data.solax_state.battery_soc is not None:
        attrs["battery_soc"] = data.solax_state.battery_soc
    
    return attrs


def _get_price_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get price attributes."""
    attrs: dict[str, Any] = {
        "tomorrow_available": data.prices.tomorrow_available,
    }
    
    if data.prices.today:
        prices_today = sorted(data.prices.today, key=lambda x: x.price)
        attrs["min_today"] = prices_today[0].price if prices_today else None
        attrs["max_today"] = prices_today[-1].price if prices_today else None
        
        # Current hour rank
        if data.prices.current_price is not None:
            rank = 1
            for hp in data.prices.today:
                if data.prices.current_price > hp.price:
                    rank += 1
            attrs["current_rank"] = rank
            attrs["total_hours"] = len(data.prices.today)
    
    return attrs


SENSOR_DESCRIPTIONS: tuple[SolarMindSensorEntityDescription, ...] = (
    SolarMindSensorEntityDescription(
        key="status",
        name="Status",
        icon="mdi:solar-power",
        value_fn=_get_status,
        attr_fn=_get_status_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="recommended_action",
        name="Recommended Action",
        icon="mdi:lightbulb-on-outline",
        value_fn=_get_recommended_action,
    ),
    SolarMindSensorEntityDescription(
        key="current_price",
        name="Current Price",
        icon="mdi:currency-eur",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="CZK/kWh",
        value_fn=_get_current_price,
        attr_fn=_get_price_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="active_strategy",
        name="Active Strategy",
        icon="mdi:strategy",
        value_fn=_get_active_strategy,
    ),
    SolarMindSensorEntityDescription(
        key="strategy_mode",
        name="Strategy Mode",
        icon="mdi:cog-outline",
        value_fn=_get_strategy_mode,
    ),
    SolarMindSensorEntityDescription(
        key="next_cheap_hour",
        name="Next Cheap Hour",
        icon="mdi:clock-outline",
        value_fn=_get_next_cheap_hour,
        attr_fn=_get_next_cheap_hour_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="cheapest_hours_today",
        name="Cheapest Hours Today",
        icon="mdi:clock-check-outline",
        value_fn=_get_cheapest_hours_today,
        attr_fn=_get_cheapest_hours_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="last_update",
        name="Last Update",
        icon="mdi:update",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_get_last_update,
    ),
    SolarMindSensorEntityDescription(
        key="next_action",
        name="Next Action",
        icon="mdi:arrow-right-bold-circle-outline",
        value_fn=_get_next_action,
    ),
    SolarMindSensorEntityDescription(
        key="battery_soc",
        name="Battery SOC",
        icon="mdi:battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=_get_battery_soc,
    ),
    SolarMindSensorEntityDescription(
        key="last_error",
        name="Last Error",
        icon="mdi:alert-circle-outline",
        entity_registry_enabled_default=False,
        value_fn=_get_last_error,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solar Mind sensors from a config entry."""
    coordinator: SolarMindCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        SolarMindSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    
    async_add_entities(entities)


class SolarMindSensor(CoordinatorEntity[SolarMindCoordinator], SensorEntity):
    """Representation of a Solar Mind sensor."""

    entity_description: SolarMindSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SolarMindCoordinator,
        entry: ConfigEntry,
        description: SolarMindSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        
        # Set unique ID
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        
        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Solar Mind"),
            manufacturer="Solar Mind",
            model="Energy Optimizer",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.coordinator.data is None or self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator.data)
