"""Solar Mind – creates hourly plan from load, generation forecast, prices, and away schedule."""

from datetime import datetime, timedelta

from .types import (
    Energy,
    PlanAction,
    Price,
    SolarMindConfig,
    Timeseries,
)

# House load patterns by hour (multiplier of average load)
LOAD_PATTERN_WEEKDAY = {
    0: 0.4, 1: 0.3, 2: 0.3, 3: 0.3, 4: 0.3, 5: 0.5,
    6: 0.8, 7: 1.2, 8: 1.0, 9: 0.7, 10: 0.6, 11: 0.6,
    12: 0.8, 13: 0.7, 14: 0.6, 15: 0.6, 16: 0.8, 17: 1.2,
    18: 1.5, 19: 1.4, 20: 1.3, 21: 1.1, 22: 0.8, 23: 0.5,
}
LOAD_PATTERN_WEEKEND = {
    0: 0.4, 1: 0.3, 2: 0.3, 3: 0.3, 4: 0.3, 5: 0.4,
    6: 0.5, 7: 0.7, 8: 0.9, 9: 1.0, 10: 1.1, 11: 1.1,
    12: 1.2, 13: 1.0, 14: 0.9, 15: 0.9, 16: 1.0, 17: 1.2,
    18: 1.4, 19: 1.3, 20: 1.2, 21: 1.0, 22: 0.8, 23: 0.5,
}


class SolarMind:
    """Pure smart control: creates hourly plan (CHARGE / SELL / BATTERY_USE / GRID_USE)."""

    def __init__(self, config: SolarMindConfig) -> None:
        self.config = config

    def create_plan(
        self,
        historical_load_data: Timeseries[Energy],
        generation_forecast: Timeseries[Energy],
        spot_prices: Timeseries[Price],
        out_of_home_schedule: Timeseries[bool],
        start_time: datetime,
        current_soc: float,
        horizon_hours: int = 48,
    ) -> Timeseries[PlanAction]:
        """
        Create an hourly plan for the next horizon_hours.

        Returns a timeseries of PlanAction: CHARGE, SELL, BATTERY_USE, GRID_USE.
        """
        print("Creating plan...")
        cfg = self.config
        start_hour = start_time.replace(minute=0, second=0, microsecond=0)
        simulated_soc = max(cfg.min_soc, min(cfg.max_soc, current_soc))

        # Collect all prices for ranking (from points in spot_prices)
        all_prices: list[float] = []
        for _start, price in spot_prices.points:
            all_prices.append(price)

        def price_rank(price: float | None) -> int:
            if price is None:
                return 24
            sorted_prices = sorted(all_prices)
            for i, p in enumerate(sorted_prices):
                if price <= p:
                    return i + 1
            return len(sorted_prices)

        def load_wh(hour: datetime) -> float:
            historical = historical_load_data.get_at(hour)
            if historical is not None:
                base = historical
            else:
                weekday = hour.weekday()
                hod = hour.hour
                mult = (
                    LOAD_PATTERN_WEEKDAY.get(hod, 1.0)
                    if weekday < 5
                    else LOAD_PATTERN_WEEKEND.get(hod, 1.0)
                )
                base = cfg.average_house_load_wh * mult
            out = out_of_home_schedule.get_at(hour)
            if out:
                base *= 1.0 - (cfg.out_of_home_load_reduce_percent / 100.0)
            return base

        def pv_wh(hour: datetime) -> float:
            value = generation_forecast.get_at(hour)
            return value if value is not None else 0.0

        def in_charge_window(hour: int) -> bool:
            s, e = cfg.charge_window_start, cfg.charge_window_end
            if s <= e:
                return s <= hour < e
            return hour >= s or hour < e

        result: list[tuple[datetime, PlanAction]] = []

        for i in range(horizon_hours):
            hour = start_hour + timedelta(hours=i)
            pv_wh_val = pv_wh(hour)
            load_wh_val = load_wh(hour)
            price = spot_prices.get_at(hour)
            net_energy = pv_wh_val - load_wh_val

            min_soc_wh = cfg.battery_capacity_wh * (cfg.min_soc / 100)
            max_soc_wh = cfg.battery_capacity_wh * (cfg.max_soc / 100)
            current_battery_wh = cfg.battery_capacity_wh * (simulated_soc / 100)
            available_charge_wh = max_soc_wh - current_battery_wh
            available_discharge_wh = current_battery_wh - min_soc_wh

            price_cheap = price is not None and price <= cfg.charge_price_threshold
            price_expensive = price is not None and price >= cfg.discharge_price_threshold
            in_window = in_charge_window(hour.hour)

            action: PlanAction

            if price_cheap and in_window and available_charge_wh > 0:
                action = PlanAction.CHARGE
                charge_wh = min(cfg.max_charge_power_w, available_charge_wh)
                soc_delta = (charge_wh * cfg.battery_efficiency) / cfg.battery_capacity_wh * 100
                simulated_soc = max(cfg.min_soc, min(cfg.max_soc, simulated_soc + soc_delta))

            elif price_expensive and cfg.discharge_allowed and available_discharge_wh > 0:
                action = PlanAction.SELL
                discharge_wh = min(cfg.max_discharge_power_w, available_discharge_wh)
                soc_delta = discharge_wh / cfg.battery_capacity_wh * 100
                simulated_soc = max(cfg.min_soc, min(cfg.max_soc, simulated_soc - soc_delta))

            elif net_energy > 0:
                if available_charge_wh > 0:
                    action = PlanAction.CHARGE
                    charge_wh = min(net_energy * cfg.battery_efficiency, available_charge_wh)
                    soc_delta = (charge_wh / cfg.battery_capacity_wh) * 100
                    simulated_soc = max(cfg.min_soc, min(cfg.max_soc, simulated_soc + soc_delta))
                else:
                    action = PlanAction.SELL

            elif available_discharge_wh > 0:
                action = PlanAction.BATTERY_USE
                needed = -net_energy
                discharge_wh = min(needed / cfg.battery_efficiency, available_discharge_wh)
                soc_delta = discharge_wh / cfg.battery_capacity_wh * 100
                simulated_soc = max(cfg.min_soc, min(cfg.max_soc, simulated_soc - soc_delta))

            else:
                action = PlanAction.GRID_USE

            result.append((hour, action))

        return Timeseries(points=result)
