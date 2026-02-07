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


def _get_plan_state(data: SolarMindData) -> str | None:
    """Get current hour's planned action from SolarMind plan (CHARGE/SELL/BATTERY_USE/GRID_USE)."""
    if not data.plan_actions:
        return None
    now = datetime.now(timezone.utc)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    for h, action in data.plan_actions:
        if h == current_hour:
            return action
    return None


def _get_plan_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get full plan schedule from SolarMind (hour -> action)."""
    if not data.plan_actions:
        return {}
    now = datetime.now(timezone.utc)
    schedule = [
        {"hour": h.isoformat(), "action": action}
        for h, action in data.plan_actions
        if h >= now
    ]
    return {"schedule": schedule[:48], "horizon_hours": len(data.plan_actions)}


def _get_current_hour_plan(data: SolarMindData) -> str | None:
    """Get current hour's planned action (legacy: from energy_plan if no plan_actions)."""
    if data.plan_actions:
        return _get_plan_state(data)
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


def _get_forecast_accuracy_pv(data: SolarMindData) -> float | None:
    """Get PV forecast accuracy percentage."""
    if not data.plan_history:
        return None
    accuracy = data.plan_history.pv_forecast_accuracy
    if accuracy is None:
        return None
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


# ============ NEW EVENT/MILESTONE/HEALTH SENSORS ============


def _get_recent_events(data: SolarMindData) -> int:
    """Get count of recent events."""
    if not data.event_log:
        return 0
    return len(data.event_log.get_recent(50))


def _get_events_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get recent events as attributes."""
    if not data.event_log:
        return {}
    recent = data.event_log.get_recent(50)
    return {
        "events": [e.to_dict() for e in recent],
        "total_count": len(data.event_log.events),
    }


def _get_latest_event(data: SolarMindData) -> str | None:
    """Get the most recent event title."""
    if not data.event_log or not data.event_log.events:
        return "No events"
    latest = data.event_log.events[-1]
    return latest.title


def _get_latest_event_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get the most recent event details."""
    if not data.event_log or not data.event_log.events:
        return {}
    latest = data.event_log.events[-1]
    return latest.to_dict()


def _get_system_health_score(data: SolarMindData) -> float | None:
    """Get the overall system health score."""
    if not data.system_health:
        return None
    return round(data.system_health.health_score, 1)


def _get_system_health_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get system health details."""
    if not data.system_health:
        return {}
    return data.system_health.to_dict()


def _get_battery_temperature(data: SolarMindData) -> float | None:
    """Get battery temperature."""
    if not data.system_health:
        return None
    return data.system_health.battery_temperature


def _get_inverter_temperature(data: SolarMindData) -> float | None:
    """Get inverter temperature."""
    if not data.system_health:
        return None
    return data.system_health.inverter_temperature


def _get_charge_cycles_today(data: SolarMindData) -> int:
    """Get number of charge cycles today."""
    if not data.system_health:
        return 0
    return data.system_health.charge_cycles_today


def _get_cycles_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get cycle count details."""
    if not data.system_health:
        return {}
    return {
        "charge_cycles": data.system_health.charge_cycles_today,
        "discharge_cycles": data.system_health.discharge_cycles_today,
        "mode_changes": data.system_health.mode_changes_today,
    }


def _get_active_warnings(data: SolarMindData) -> int:
    """Get number of active warnings."""
    if not data.system_health:
        return 0
    return len(data.system_health.active_warnings)


def _get_warnings_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get active warnings details."""
    if not data.system_health:
        return {}
    return {
        "warnings": data.system_health.active_warnings,
        "recent_errors": data.system_health.recent_errors[-5:],
    }


def _get_next_milestone(data: SolarMindData) -> str | None:
    """Get the next upcoming milestone."""
    if not data.milestones:
        return "No milestones"
    return data.milestones[0].title


def _get_milestone_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get milestone details."""
    if not data.milestones:
        return {}
    return {
        "milestones": [m.to_dict() for m in data.milestones],
        "next_milestone_time": data.milestones[0].timestamp.isoformat() if data.milestones else None,
    }


def _get_best_water_heater_time(data: SolarMindData) -> str | None:
    """Get the best time to run water heater."""
    if not data.milestones:
        return None
    for m in data.milestones:
        if m.milestone_type == "best_appliance_time" and "water" in m.data.get("appliance", "").lower():
            return m.timestamp.strftime("%H:%M")
    # If no specific milestone, find best surplus hour
    if data.energy_plan and data.energy_plan.entries:
        now = datetime.now(timezone.utc)
        best_entry = None
        best_surplus = 0
        for entry in data.energy_plan.entries:
            if entry.hour > now:
                surplus = entry.pv_forecast_wh - entry.load_forecast_wh
                if surplus > best_surplus:
                    best_surplus = surplus
                    best_entry = entry
        if best_entry and best_surplus > 1000:  # At least 1kWh surplus
            return best_entry.hour.strftime("%H:%M")
    return None


def _get_appliance_time_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get appliance timing details."""
    if not data.milestones:
        return {}
    appliance_times = {}
    for m in data.milestones:
        if m.milestone_type == "best_appliance_time":
            appliance_name = m.data.get("appliance", "Unknown")
            appliance_times[appliance_name] = {
                "time": m.timestamp.strftime("%H:%M"),
                "date": m.timestamp.strftime("%Y-%m-%d"),
                "power_w": m.data.get("power_w"),
            }
    return {"appliance_recommendations": appliance_times}


def _get_surplus_start_time(data: SolarMindData) -> str | None:
    """Get when energy surplus is expected to start."""
    if not data.milestones:
        return None
    for m in data.milestones:
        if m.milestone_type == "surplus_start":
            return m.timestamp.strftime("%H:%M")
    return None


def _get_surplus_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get surplus timing details."""
    if not data.energy_plan or not data.energy_plan.entries:
        return {}
    now = datetime.now(timezone.utc)
    surplus_hours = []
    for entry in data.energy_plan.entries:
        if entry.hour > now and entry.pv_forecast_wh > entry.load_forecast_wh:
            surplus_hours.append({
                "hour": entry.hour.strftime("%H:%M"),
                "surplus_wh": round(entry.pv_forecast_wh - entry.load_forecast_wh, 1),
                "pv_wh": round(entry.pv_forecast_wh, 1),
                "load_wh": round(entry.load_forecast_wh, 1),
            })
    return {
        "surplus_hours": surplus_hours[:12],
        "total_surplus_hours": len(surplus_hours),
        "total_surplus_wh": sum(h["surplus_wh"] for h in surplus_hours),
    }


def _get_away_periods_count(data: SolarMindData) -> int:
    """Get number of configured away periods."""
    if not data.user_preferences:
        return 0
    return len(data.user_preferences.away_periods)


def _get_away_periods_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get away periods details."""
    if not data.user_preferences:
        return {}
    now = datetime.now(timezone.utc)
    active = data.user_preferences.get_active_away_period(now)
    return {
        "away_periods": [p.to_dict() for p in data.user_preferences.away_periods],
        "is_away": active is not None,
        "active_period": active.to_dict() if active else None,
    }


def _get_energy_flow_state(data: SolarMindData) -> str:
    """Get current energy flow state description."""
    if not data.strategy_output:
        return "unknown"
    
    status = data.strategy_output.status.value
    power = data.strategy_output.power_w or 0
    
    if status == "charging":
        return f"Grid → Battery ({abs(power)}W)"
    elif status == "discharging":
        return f"Battery → Grid ({abs(power)}W)"
    elif status == "self_use":
        return "Solar → Home/Battery"
    elif status == "house_from_grid":
        return "Grid → Home"
    return status


def _get_energy_flow_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get detailed energy flow information."""
    attrs: dict[str, Any] = {}
    
    if data.solax_state:
        attrs["battery_soc"] = data.solax_state.battery_soc
        attrs["current_mode"] = data.solax_state.current_mode
        attrs["active_power"] = data.solax_state.active_power
        attrs["grid_import"] = data.solax_state.grid_import
        attrs["grid_export"] = data.solax_state.grid_export
        attrs["house_load"] = data.solax_state.house_load
    
    if data.strategy_output:
        attrs["status"] = data.strategy_output.status.value
        attrs["reason"] = data.strategy_output.reason
    
    if data.prices:
        attrs["current_price"] = data.prices.current_price
    
    return attrs


def _get_hourly_plan_json(data: SolarMindData) -> str | None:
    """Get the full hourly plan as JSON string for dashboard visualization."""
    if not data.energy_plan or not data.energy_plan.entries:
        return None
    return str(len(data.energy_plan.entries)) + " hours"


def _get_hourly_plan_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get hourly plan for visualization. Limited to next 24h to stay under Recorder 16KB limit."""
    if not data.energy_plan or not data.energy_plan.entries:
        return {}
    now = datetime.now(timezone.utc)
    # Only include future + next 24h to keep attributes under 16KB
    entries_24h = [e for e in data.energy_plan.entries if e.hour >= now][:24]
    plan_dicts = [e.to_dict() for e in entries_24h]
    return {
        "plan": plan_dicts,
        "summary": {
            "total_pv_kwh": round(data.energy_plan.total_pv_forecast_wh / 1000, 2),
            "total_load_kwh": round(data.energy_plan.total_load_forecast_wh / 1000, 2),
            "total_import_kwh": round(data.energy_plan.total_grid_import_wh / 1000, 2),
            "total_export_kwh": round(data.energy_plan.total_grid_export_wh / 1000, 2),
            "estimated_cost": round(data.energy_plan.estimated_cost, 2),
            "estimated_revenue": round(data.energy_plan.estimated_revenue, 2),
        },
    }


def _get_price_forecast_json(data: SolarMindData) -> str | None:
    """Get price forecast summary (clear label: hours of data)."""
    if not data.prices.today:
        return "No data"
    today_h = len(data.prices.today)
    tomorrow_h = len(data.prices.tomorrow)
    if tomorrow_h:
        return f"{today_h}h today, {tomorrow_h}h tomorrow"
    return f"{today_h}h today"


def _get_price_forecast_attrs(data: SolarMindData) -> dict[str, Any]:
    """Get price forecast details for visualization."""
    today_prices = [{"hour": p.start.hour, "price": p.price} for p in data.prices.today]
    tomorrow_prices = [{"hour": p.start.hour, "price": p.price} for p in data.prices.tomorrow]
    
    return {
        "today": today_prices,
        "tomorrow": tomorrow_prices,
        "current_price": data.prices.current_price,
        "tomorrow_available": data.prices.tomorrow_available,
        "cheapest_today": min(today_prices, key=lambda x: x["price"]) if today_prices else None,
        "most_expensive_today": max(today_prices, key=lambda x: x["price"]) if today_prices else None,
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
    # ============ PLAN ENTITY (SolarMind output) ============
    SolarMindSensorEntityDescription(
        key="plan",
        name="Plan",
        icon="mdi:calendar-clock",
        value_fn=_get_plan_state,
        attr_fn=_get_plan_attrs,
    ),
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
        key="next_action",
        name="Next Action",
        icon="mdi:arrow-right-bold-circle-outline",
        state_class=None,  # Future data
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
        state_class=None,  # Forecast: avoid history-stats in UI
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_get_pv_forecast_today,
        attr_fn=_get_pv_forecast_today_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="pv_forecast_tomorrow",
        name="PV Forecast Tomorrow",
        icon="mdi:solar-power-variant-outline",
        device_class=SensorDeviceClass.ENERGY,
        state_class=None,  # Forecast
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_get_pv_forecast_tomorrow,
        attr_fn=_get_pv_forecast_tomorrow_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="load_forecast_today",
        name="Load Forecast Today",
        icon="mdi:home-lightning-bolt",
        device_class=SensorDeviceClass.ENERGY,
        state_class=None,  # Forecast
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=_get_load_forecast_today,
        attr_fn=_get_load_forecast_today_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="next_planned_charge",
        name="Next Planned Charge",
        icon="mdi:battery-charging-high",
        state_class=None,  # Future data
        value_fn=_get_next_planned_charge,
        attr_fn=_get_next_planned_charge_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="next_planned_discharge",
        name="Next Planned Discharge",
        icon="mdi:battery-arrow-down",
        state_class=None,  # Future data
        value_fn=_get_next_planned_discharge,
        attr_fn=_get_next_planned_discharge_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="predicted_soc_6h",
        name="Predicted SOC (6h)",
        icon="mdi:battery-clock",
        device_class=SensorDeviceClass.BATTERY,
        state_class=None,  # Forecast: avoid history-stats
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
        state_class=None,  # Plan metadata: avoid history-stats
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
    # ============ NEW EVENT/MILESTONE/HEALTH SENSORS ============
    SolarMindSensorEntityDescription(
        key="recent_events_count",
        name="Recent Events",
        icon="mdi:timeline-clock-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_recent_events,
        attr_fn=_get_events_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="latest_event",
        name="Latest Event",
        icon="mdi:bell-outline",
        value_fn=_get_latest_event,
        attr_fn=_get_latest_event_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="system_health_score",
        name="System Health",
        icon="mdi:heart-pulse",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=_get_system_health_score,
        attr_fn=_get_system_health_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="battery_temperature",
        name="Battery Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        entity_registry_enabled_default=False,
        value_fn=_get_battery_temperature,
    ),
    SolarMindSensorEntityDescription(
        key="inverter_temperature",
        name="Inverter Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        entity_registry_enabled_default=False,
        value_fn=_get_inverter_temperature,
    ),
    SolarMindSensorEntityDescription(
        key="charge_cycles_today",
        name="Charge Cycles Today",
        icon="mdi:battery-charging-high",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_get_charge_cycles_today,
        attr_fn=_get_cycles_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="active_warnings",
        name="Active Warnings",
        icon="mdi:alert-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_active_warnings,
        attr_fn=_get_warnings_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="next_milestone",
        name="Next Milestone",
        icon="mdi:flag-checkered",
        state_class=None,  # Future data
        value_fn=_get_next_milestone,
        attr_fn=_get_milestone_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="best_water_heater_time",
        name="Best Time for Water Heater",
        icon="mdi:water-boiler",
        state_class=None,  # Future time
        value_fn=_get_best_water_heater_time,
        attr_fn=_get_appliance_time_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="surplus_start_time",
        name="Surplus Start Time",
        icon="mdi:weather-sunny-alert",
        state_class=None,  # Future time
        value_fn=_get_surplus_start_time,
        attr_fn=_get_surplus_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="away_periods",
        name="Away Periods",
        icon="mdi:home-export-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_away_periods_count,
        attr_fn=_get_away_periods_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="energy_flow",
        name="Energy Flow",
        icon="mdi:transmission-tower",
        value_fn=_get_energy_flow_state,
        attr_fn=_get_energy_flow_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="hourly_plan",
        name="Hourly Plan",
        icon="mdi:calendar-text",
        state_class=None,  # Future plan: use forecast card
        value_fn=_get_hourly_plan_json,
        attr_fn=_get_hourly_plan_attrs,
    ),
    SolarMindSensorEntityDescription(
        key="price_forecast",
        name="Price Forecast",
        icon="mdi:chart-line-variant",
        state_class=None,  # Future data: use price/cheapest card
        value_fn=_get_price_forecast_json,
        attr_fn=_get_price_forecast_attrs,
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
