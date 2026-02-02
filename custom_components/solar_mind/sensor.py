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

from .const import DOMAIN, STRATEGY_DISPLAY_NAMES, SystemStatus
from .coordinator import SolarMindCoordinator
from .models import PlannedAction, SolarMindData


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


def _get_next_action(data: SolarMindData) -> str | None:
    """Get next planned action."""
    if data.strategy_output:
        return data.strategy_output.reason
    return None


def _get_battery_soc(data: SolarMindData) -> float | None:
    """Get battery SOC from last read."""
    return data.solax_state.battery_soc


# ============ NEW FORECAST/PLAN SENSORS ============


def _get_pv_forecast_today(data: SolarMindData) -> float | None:
    """Get total PV forecast for today in kWh."""
    if not data.energy_plan or not data.energy_plan.entries:
        return None
    now = datetime.now(timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59)
    total_wh = sum(
        e.pv_forecast_wh
        for e in data.energy_plan.entries
        if e.hour.date() == now.date() and e.hour <= today_end
    )
    return round(total_wh / 1000, 2)


def _get_pv_forecast_today_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get PV forecast details for today."""
    if not data.energy_plan or not data.energy_plan.entries:
        return {}
    now = datetime.now(timezone.utc)
    hourly = []
    for e in data.energy_plan.entries:
        if e.hour.date() == now.date():
            hourly.append({
                "hour": e.hour.strftime("%H:00"),
                "pv_wh": round(e.pv_forecast_wh, 1),
                "solar_potential": round(e.solar_potential, 2),
                "condition": e.weather_condition,
            })
    return {"hourly_forecast": hourly}


def _get_pv_forecast_tomorrow(data: SolarMindData) -> float | None:
    """Get total PV forecast for tomorrow in kWh."""
    if not data.energy_plan or not data.energy_plan.entries:
        return None
    now = datetime.now(timezone.utc)
    tomorrow = now.date() + timedelta(days=1)
    total_wh = sum(
        e.pv_forecast_wh
        for e in data.energy_plan.entries
        if e.hour.date() == tomorrow
    )
    if total_wh == 0:
        return None
    return round(total_wh / 1000, 2)


def _get_pv_forecast_tomorrow_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get PV forecast details for tomorrow."""
    if not data.energy_plan or not data.energy_plan.entries:
        return {}
    now = datetime.now(timezone.utc)
    tomorrow = now.date() + timedelta(days=1)
    hourly = []
    for e in data.energy_plan.entries:
        if e.hour.date() == tomorrow:
            hourly.append({
                "hour": e.hour.strftime("%H:00"),
                "pv_wh": round(e.pv_forecast_wh, 1),
                "solar_potential": round(e.solar_potential, 2),
                "condition": e.weather_condition,
            })
    return {"hourly_forecast": hourly, "available": len(hourly) > 0}


def _get_load_forecast_today(data: SolarMindData) -> float | None:
    """Get total load forecast for today in kWh."""
    if not data.energy_plan or not data.energy_plan.entries:
        return None
    now = datetime.now(timezone.utc)
    total_wh = sum(
        e.load_forecast_wh
        for e in data.energy_plan.entries
        if e.hour.date() == now.date()
    )
    return round(total_wh / 1000, 2)


def _get_load_forecast_today_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get load forecast details for today."""
    if not data.energy_plan or not data.energy_plan.entries:
        return {}
    now = datetime.now(timezone.utc)
    hourly = []
    for e in data.energy_plan.entries:
        if e.hour.date() == now.date():
            hourly.append({
                "hour": e.hour.strftime("%H:00"),
                "load_wh": round(e.load_forecast_wh, 1),
            })
    return {"hourly_forecast": hourly}


def _get_next_planned_charge(data: SolarMindData) -> str:
    """Get next planned charge time."""
    if not data.energy_plan:
        return "—"
    now = datetime.now(timezone.utc)
    for e in data.energy_plan.entries:
        if e.hour > now and e.action == PlannedAction.CHARGE:
            return e.hour.strftime("%H:%M")
    return "—"


def _get_next_planned_charge_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get next planned charge details."""
    if not data.energy_plan:
        return {}
    now = datetime.now(timezone.utc)
    charge_hours = []
    for e in data.energy_plan.entries:
        if e.hour > now and e.action == PlannedAction.CHARGE:
            charge_hours.append({
                "time": e.hour.strftime("%H:%M"),
                "date": e.hour.strftime("%Y-%m-%d"),
                "price": round(e.price, 4) if e.price else None,
                "reason": e.reason,
                "charge_wh": round(e.planned_battery_charge_wh, 1),
            })
    return {
        "upcoming_charge_hours": charge_hours[:12],
        "total_charge_hours": len(charge_hours),
    }


def _get_next_planned_discharge(data: SolarMindData) -> str:
    """Get next planned discharge time."""
    if not data.energy_plan:
        return "—"
    now = datetime.now(timezone.utc)
    for e in data.energy_plan.entries:
        if e.hour > now and e.action == PlannedAction.DISCHARGE:
            return e.hour.strftime("%H:%M")
    return "—"


def _get_next_planned_discharge_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get next planned discharge details."""
    if not data.energy_plan:
        return {}
    now = datetime.now(timezone.utc)
    discharge_hours = []
    for e in data.energy_plan.entries:
        if e.hour > now and e.action == PlannedAction.DISCHARGE:
            discharge_hours.append({
                "time": e.hour.strftime("%H:%M"),
                "date": e.hour.strftime("%Y-%m-%d"),
                "price": round(e.price, 4) if e.price else None,
                "reason": e.reason,
                "discharge_wh": round(e.planned_battery_discharge_wh, 1),
            })
    return {
        "upcoming_discharge_hours": discharge_hours[:12],
        "total_discharge_hours": len(discharge_hours),
    }


def _get_predicted_soc_6h(data: SolarMindData) -> float | None:
    """Get predicted battery SOC in 6 hours."""
    if not data.energy_plan or not data.energy_plan.entries:
        return None
    now = datetime.now(timezone.utc)
    target_time = now + timedelta(hours=6)
    for e in data.energy_plan.entries:
        if e.hour <= target_time < e.hour + timedelta(hours=1):
            return round(e.predicted_soc, 1)
    return None


def _get_predicted_soc_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get predicted SOC timeline."""
    if not data.energy_plan or not data.energy_plan.entries:
        return {}
    now = datetime.now(timezone.utc)
    soc_timeline = []
    for e in data.energy_plan.entries[:24]:  # Next 24 hours
        if e.hour >= now:
            soc_timeline.append({
                "hour": e.hour.strftime("%H:%M"),
                "soc": round(e.predicted_soc, 1),
                "action": e.action.value,
            })
    return {"soc_forecast": soc_timeline}


def _get_estimated_daily_cost(data: SolarMindData) -> float | None:
    """Get estimated daily grid cost."""
    if not data.energy_plan:
        return None
    return round(data.energy_plan.estimated_cost, 2)


def _get_cost_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get cost/revenue details."""
    if not data.energy_plan:
        return {}
    return {
        "estimated_revenue": round(data.energy_plan.estimated_revenue, 2),
        "net_cost": round(
            data.energy_plan.estimated_cost - data.energy_plan.estimated_revenue, 2
        ),
        "grid_import_kwh": round(data.energy_plan.total_grid_import_wh / 1000, 2),
        "grid_export_kwh": round(data.energy_plan.total_grid_export_wh / 1000, 2),
    }


def _get_estimated_daily_revenue(data: SolarMindData) -> float | None:
    """Get estimated daily grid revenue."""
    if not data.energy_plan:
        return None
    return round(data.energy_plan.estimated_revenue, 2)


def _get_current_hour_plan(data: SolarMindData) -> str | None:
    """Get current hour's planned action."""
    if not data.energy_plan:
        return None
    now = datetime.now(timezone.utc)
    entry = data.energy_plan.get_entry_at(now)
    if entry:
        return entry.action.value
    return None


def _get_current_hour_plan_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get current hour's plan details."""
    if not data.energy_plan:
        return {}
    now = datetime.now(timezone.utc)
    entry = data.energy_plan.get_entry_at(now)
    if not entry:
        return {}
    return {
        "pv_forecast_wh": round(entry.pv_forecast_wh, 1),
        "load_forecast_wh": round(entry.load_forecast_wh, 1),
        "price": round(entry.price, 4) if entry.price else None,
        "grid_import_wh": round(entry.planned_grid_import_wh, 1),
        "grid_export_wh": round(entry.planned_grid_export_wh, 1),
        "battery_charge_wh": round(entry.planned_battery_charge_wh, 1),
        "battery_discharge_wh": round(entry.planned_battery_discharge_wh, 1),
        "predicted_soc": round(entry.predicted_soc, 1),
        "reason": entry.reason,
        "weather": entry.weather_condition,
        "solar_potential": round(entry.solar_potential, 2),
    }


def _get_forecast_accuracy_pv(data: SolarMindData) -> float | str:
    """Get PV forecast accuracy percentage."""
    if not data.plan_history:
        return "No data"
    accuracy = data.plan_history.pv_forecast_accuracy
    if accuracy is None:
        return "No data"
    return round(accuracy, 1)


def _get_accuracy_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get forecast accuracy details."""
    if not data.plan_history:
        return {}
    recent = data.plan_history.get_recent(24)
    pv_errors = []
    load_errors = []
    for c in recent:
        if c.pv_error_wh is not None:
            pv_errors.append(c.pv_error_wh)
        if c.load_error_wh is not None:
            load_errors.append(c.load_error_wh)
    return {
        "pv_accuracy_pct": data.plan_history.pv_forecast_accuracy,
        "load_accuracy_pct": data.plan_history.load_forecast_accuracy,
        "samples_24h": len(recent),
        "avg_pv_error_wh": round(sum(pv_errors) / len(pv_errors), 1) if pv_errors else None,
        "avg_load_error_wh": round(sum(load_errors) / len(load_errors), 1) if load_errors else None,
    }


def _get_plan_horizon(data: SolarMindData) -> int | None:
    """Get how many hours the plan extends."""
    if not data.energy_plan or not data.energy_plan.entries:
        return None
    return len(data.energy_plan.entries)


def _get_plan_horizon_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get plan horizon details."""
    if not data.energy_plan or not data.energy_plan.entries:
        return {}
    now = datetime.now(timezone.utc)
    return {
        "plan_created": data.energy_plan.created_at.isoformat() if data.energy_plan.created_at else None,
        "plan_ends": data.energy_plan.entries[-1].hour.isoformat() if data.energy_plan.entries else None,
        "tomorrow_available": any(
            e.hour.date() > now.date() for e in data.energy_plan.entries
        ),
    }


def _get_historical_comparison(data: SolarMindData) -> str | None:
    """Get summary of recent prediction accuracy."""
    if not data.plan_history or not data.plan_history.comparisons:
        return "No data"
    accuracy = data.plan_history.pv_forecast_accuracy
    if accuracy is not None:
        return f"{accuracy:.0f}%"
    return "Calculating..."


def _get_historical_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get historical comparison details."""
    if not data.plan_history or not data.plan_history.comparisons:
        return {}
    recent = data.plan_history.get_recent(24)
    comparisons = []
    for c in recent:
        if c.predicted and c.actual:
            comparisons.append({
                "hour": c.hour.strftime("%Y-%m-%d %H:00"),
                "predicted_pv_wh": round(c.predicted.pv_forecast_wh, 1),
                "actual_pv_wh": round(c.actual.pv_actual_wh, 1) if c.actual.pv_actual_wh else None,
                "pv_error_wh": round(c.pv_error_wh, 1) if c.pv_error_wh is not None else None,
                "predicted_soc": round(c.predicted.predicted_soc, 1),
                "actual_soc": round(c.actual.battery_soc_end, 1) if c.actual.battery_soc_end else None,
            })
    return {
        "recent_comparisons": comparisons,
        "total_samples": len(data.plan_history.comparisons),
    }


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
    # ============ EXISTING SENSORS ============
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
    # ============ NEW FORECAST/PLAN SENSORS ============
    SolarMindSensorEntityDescription(
        key="pv_forecast_today",
        name="PV Forecast Today",
        icon="mdi:solar-power-variant",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_get_pv_forecast_today,
        attr_fn=_get_pv_forecast_today_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="pv_forecast_tomorrow",
        name="PV Forecast Tomorrow",
        icon="mdi:solar-power-variant-outline",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_get_pv_forecast_tomorrow,
        attr_fn=_get_pv_forecast_tomorrow_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="load_forecast_today",
        name="Load Forecast Today",
        icon="mdi:home-lightning-bolt",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_get_load_forecast_today,
        attr_fn=_get_load_forecast_today_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="next_planned_charge",
        name="Next Planned Charge",
        icon="mdi:battery-charging-high",
        value_fn=_get_next_planned_charge,
        attr_fn=_get_next_planned_charge_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="next_planned_discharge",
        name="Next Planned Discharge",
        icon="mdi:battery-arrow-down",
        value_fn=_get_next_planned_discharge,
        attr_fn=_get_next_planned_discharge_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="predicted_soc_6h",
        name="Predicted SOC (6h)",
        icon="mdi:battery-clock",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=_get_predicted_soc_6h,
        attr_fn=_get_predicted_soc_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="estimated_daily_cost",
        name="Estimated Daily Cost",
        icon="mdi:cash-minus",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CZK",
        value_fn=_get_estimated_daily_cost,
        attr_fn=_get_cost_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="estimated_daily_revenue",
        name="Estimated Daily Revenue",
        icon="mdi:cash-plus",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CZK",
        value_fn=_get_estimated_daily_revenue,
    ),
    SolarMindSensorEntityDescription(
        key="current_hour_plan",
        name="Current Hour Plan",
        icon="mdi:clock-time-four",
        value_fn=_get_current_hour_plan,
        attr_fn=_get_current_hour_plan_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="forecast_accuracy",
        name="Forecast Accuracy",
        icon="mdi:chart-line",
        state_class=None,
        native_unit_of_measurement="%",
        value_fn=_get_forecast_accuracy_pv,
        attr_fn=_get_accuracy_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="plan_horizon",
        name="Plan Horizon",
        icon="mdi:calendar-clock",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="hours",
        value_fn=_get_plan_horizon,
        attr_fn=_get_plan_horizon_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="historical_comparison",
        name="Historical Accuracy",
        icon="mdi:history",
        value_fn=_get_historical_comparison,
        attr_fn=_get_historical_attrs,
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
