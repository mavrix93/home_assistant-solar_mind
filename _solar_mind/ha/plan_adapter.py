"""Adapter: build mind inputs from HA data and call SolarMind.create_plan."""

from datetime import datetime, timedelta, timezone
from typing import Any

from ..const import (
    CONF_AVERAGE_HOUSE_LOAD,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_EFFICIENCY,
    CONF_CHARGE_PRICE_THRESHOLD,
    CONF_CHARGE_WINDOW_END,
    CONF_CHARGE_WINDOW_START,
    CONF_DISCHARGE_ALLOWED,
    CONF_DISCHARGE_PRICE_THRESHOLD,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_PV_POWER,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    DEFAULT_AVERAGE_HOUSE_LOAD,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_EFFICIENCY,
    DEFAULT_CHARGE_PRICE_THRESHOLD,
    DEFAULT_CHARGE_WINDOW_END,
    DEFAULT_CHARGE_WINDOW_START,
    DEFAULT_DISCHARGE_ALLOWED,
    DEFAULT_DISCHARGE_PRICE_THRESHOLD,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_PV_POWER,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
)
from ..mind import PlanAction, SolarMind, SolarMindConfig, Timeseries
from ..mind.models import PriceData, SolarMindData, WeatherForecast


def _condition_to_cloud_coverage(condition: str) -> float:
    """Map weather condition to 0–1 (1 = clear, 0 = overcast)."""
    c = (condition or "").lower()
    if c in ("sunny", "clear", "clear-night"):
        return 1.0
    if c in ("partlycloudy", "partly_cloudy"):
        return 0.65
    if c == "cloudy":
        return 0.25
    if c in ("rainy", "pouring", "lightning-rainy"):
        return 0.1
    if c in ("snowy", "snowy-rainy"):
        return 0.15
    if c in ("fog", "hail"):
        return 0.2
    return 0.5


def _config_from_options(options: dict[str, Any]) -> SolarMindConfig:
    """Build SolarMindConfig from integration options."""
    return SolarMindConfig(
        battery_capacity_wh=float(options.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)),
        min_soc=float(options.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)),
        max_soc=float(options.get(CONF_MAX_SOC, DEFAULT_MAX_SOC)),
        max_pv_power_w=float(options.get(CONF_MAX_PV_POWER, DEFAULT_MAX_PV_POWER)),
        average_house_load_wh=float(options.get(CONF_AVERAGE_HOUSE_LOAD, DEFAULT_AVERAGE_HOUSE_LOAD)),
        battery_efficiency=float(options.get(CONF_BATTERY_EFFICIENCY, DEFAULT_BATTERY_EFFICIENCY)),
        charge_price_threshold=float(options.get(CONF_CHARGE_PRICE_THRESHOLD, DEFAULT_CHARGE_PRICE_THRESHOLD)),
        discharge_price_threshold=float(options.get(CONF_DISCHARGE_PRICE_THRESHOLD, DEFAULT_DISCHARGE_PRICE_THRESHOLD)),
        charge_window_start=int(options.get(CONF_CHARGE_WINDOW_START, DEFAULT_CHARGE_WINDOW_START)),
        charge_window_end=int(options.get(CONF_CHARGE_WINDOW_END, DEFAULT_CHARGE_WINDOW_END)),
        discharge_allowed=bool(options.get(CONF_DISCHARGE_ALLOWED, DEFAULT_DISCHARGE_ALLOWED)),
        max_charge_power_w=float(options.get(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER)),
        max_discharge_power_w=float(options.get(CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER)),
    )


def build_historical_load_timeseries(plan_history: Any) -> Timeseries[float]:
    """Build Timeseries[Energy] from plan history actuals (hour -> avg load Wh)."""
    slot_sums: dict[tuple[int, int], list[float]] = {}
    for comp in getattr(plan_history, "comparisons", []):
        actual = getattr(comp, "actual", None)
        if not actual or getattr(actual, "load_actual_wh", None) is None:
            continue
        hour = getattr(comp, "hour", None)
        if not hour:
            continue
        key = (hour.hour, hour.weekday())
        slot_sums.setdefault(key, []).append(actual.load_actual_wh)
    avg_by_slot = {
        key: sum(v) / len(v)
        for key, values in slot_sums.items()
        for v in [values]
        if values
    }
    if not avg_by_slot:
        return Timeseries(points=[])

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=7)).replace(minute=0, second=0, microsecond=0)
    points: list[tuple[datetime, float]] = []
    for i in range(24 * 7):
        h = start + timedelta(hours=i)
        key = (h.hour, h.weekday())
        if key in avg_by_slot:
            points.append((h, avg_by_slot[key]))
    return Timeseries(points=points)


def build_weather_timeseries(weather: WeatherForecast, start: datetime, horizon_hours: int) -> Timeseries[float]:
    """Build Timeseries[CloudCoverage] from HA weather forecast."""
    hourly = getattr(weather, "hourly", []) or []
    end = start + timedelta(hours=horizon_hours)
    points: list[tuple[datetime, float]] = []
    for entry in hourly:
        dt = entry.get("datetime")
        if isinstance(dt, datetime):
            if start <= dt < end:
                points.append((dt, _condition_to_cloud_coverage(entry.get("condition", ""))))
        elif isinstance(dt, str):
            try:
                parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                if start <= parsed < end:
                    points.append((parsed, _condition_to_cloud_coverage(entry.get("condition", ""))))
            except (ValueError, TypeError):
                pass
    if not points:
        points = [(start + timedelta(hours=i), 0.5) for i in range(horizon_hours)]
    return Timeseries(points=points)


def build_prices_timeseries(prices: PriceData, start: datetime, horizon_hours: int) -> Timeseries[float]:
    """Build Timeseries[Price] from HA price data."""
    points: list[tuple[datetime, float]] = []
    get_price_at = getattr(prices, "get_price_at", None)
    for i in range(horizon_hours):
        h = start + timedelta(hours=i)
        price = get_price_at(h) if get_price_at else None
        points.append((h, price if price is not None else 0.0))
    return Timeseries(points=points)


def build_out_of_home_timeseries(
    user_preferences: Any,
    start: datetime,
    horizon_hours: int,
) -> Timeseries[bool]:
    """Build Timeseries[bool] from away periods."""
    away_periods = getattr(user_preferences, "away_periods", []) or []
    points: list[tuple[datetime, bool]] = []
    for i in range(horizon_hours):
        h = start + timedelta(hours=i)
        out = any(getattr(p, "is_active", lambda t: False)(h) for p in away_periods)
        points.append((h, out))
    return Timeseries(points=points)


def create_plan_from_ha_data(
    options: dict[str, Any],
    data: SolarMindData,
    start_time: datetime,
    current_soc: float,
    horizon_hours: int = 48,
) -> list[tuple[datetime, str]]:
    """
    Build mind inputs from HA data, call SolarMind.create_plan, return list of (hour, action).
    """
    config = _config_from_options(options)
    solar_mind = SolarMind(config)

    historical_load = build_historical_load_timeseries(data.plan_history)
    prices_ts = build_prices_timeseries(data.prices, start_time, horizon_hours)
    out_of_home_ts = build_out_of_home_timeseries(data.user_preferences, start_time, horizon_hours)

    generation_forecast = data.generation_forecast if data.generation_forecast is not None else Timeseries(points=[])

    plan = solar_mind.create_plan(
        historical_load_data=historical_load,
        generation_forecast=generation_forecast,
        spot_prices=prices_ts,
        out_of_home_schedule=out_of_home_ts,
        start_time=start_time,
        current_soc=current_soc,
        horizon_hours=horizon_hours,
    )

    return [(h, a.value) for h, a in plan.points]
