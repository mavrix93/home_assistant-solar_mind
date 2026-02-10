"""Sensor platform for Solar Mind integration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.solar_mind.ha.const import DOMAIN

from .ha.coordinator import SolarMindCoordinator
from .mind.models import SolarMindData




def _get_current_price(data: SolarMindData) -> float | None:
    """Get current spot price."""
    return data.prices.current_price



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
    
    now = datetime.now(timezone.utc)
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
    
    now = datetime.now(timezone.utc)
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




# ============ GENERATION FORECAST SENSOR (forecast.solar) ============


def _get_generation_forecast_current(data: SolarMindData) -> float | None:
    """Get predicted PV generation Wh for the current hour from forecast.solar."""
    if not data.generation_forecast:
        return None
    now = datetime.now(timezone.utc)
    value = data.generation_forecast.get_at(now)
    return round(value, 1) if value is not None else 0.0


def _get_generation_forecast_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get full generation forecast timeseries as attributes."""
    if not data.generation_forecast:
        return {}
    now = datetime.now(timezone.utc)
    hourly = []
    total_today_wh = 0.0
    total_tomorrow_wh = 0.0
    tomorrow = now.date() + timedelta(days=1)
    for dt, wh in data.generation_forecast.points:
        hourly.append({
            "hour": dt.isoformat(),
            "wh": round(wh, 1),
        })
        if dt.date() == now.date():
            total_today_wh += wh
        elif dt.date() == tomorrow:
            total_tomorrow_wh += wh
    return {
        "hourly_forecast": hourly,
        "total_today_wh": round(total_today_wh, 1),
        "total_today_kwh": round(total_today_wh / 1000, 2),
        "total_tomorrow_wh": round(total_tomorrow_wh, 1),
        "total_tomorrow_kwh": round(total_tomorrow_wh / 1000, 2),
        "source": "forecast.solar",
    }



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

@dataclass(frozen=True, kw_only=True)
class SolarMindSensorEntityDescription(SensorEntityDescription):
    """Describes a Solar Mind sensor entity."""

    value_fn: Callable[[SolarMindData], Any]
    attr_fn: Callable[[SolarMindData], dict[str, Any]] | None = None

SENSOR_DESCRIPTIONS: tuple[SolarMindSensorEntityDescription, ...] = (
   
    SolarMindSensorEntityDescription(
        key="current_price",
        name="Current Price",
        icon="mdi:currency-eur",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="CZK/kWh",
        value_fn=_get_current_price,
        attr_fn=_get_price_attrs,
    ),
   
    SolarMindSensorEntityDescription(
        key="next_cheap_hour",
        name="Next Cheap Hour",
        icon="mdi:clock-outline",
        state_class=None,  # Future data: avoid history-stats in UI
        value_fn=_get_next_cheap_hour,
        attr_fn=_get_next_cheap_hour_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="cheapest_hours_today",
        name="Cheapest Hours Today",
        icon="mdi:clock-check-outline",
        state_class=None,  # Future data: use custom card, not history
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
        key="last_error",
        name="Last Error",
        icon="mdi:alert-circle-outline",
        entity_registry_enabled_default=False,
        value_fn=_get_last_error,
    ),
    # ============ GENERATION FORECAST (forecast.solar) ============
    SolarMindSensorEntityDescription(
        key="generation_forecast",
        name="PV Generation Forecast",
        icon="mdi:solar-power",
        device_class=SensorDeviceClass.ENERGY,
        state_class=None,  # Forecast: avoid history-stats
        native_unit_of_measurement="Wh",
        value_fn=_get_generation_forecast_current,
        attr_fn=_get_generation_forecast_attrs,
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
