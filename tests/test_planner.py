"""Tests for Solar Mind energy planner module."""

from datetime import datetime, timedelta

import pytest

from custom_components.solar_mind.models import (
    EnergyPlan,
    HourlyActual,
    HourlyPlanEntry,
    HourlyPrice,
    PlannedAction,
    PlanHistory,
    PredictionComparison,
    PriceData,
    SolaxState,
    WeatherForecast,
)
from custom_components.solar_mind.planner import (
    EnergyPlanner,
    _build_historical_load_profile,
    record_actual_hour,
)


class TestEnergyPlanner:
    """Test EnergyPlanner class."""

    @pytest.fixture
    def planner_options(self) -> dict:
        """Default planner options for tests."""
        return {
            "battery_capacity": 10000,  # 10 kWh
            "max_pv_power": 10000,  # 10 kW peak
            "average_house_load": 500,  # 500W average
            "battery_efficiency": 0.95,
            "min_soc": 10,
            "max_soc": 95,
            "max_charge_power": 3000,
            "max_discharge_power": 3000,
            "charge_price_threshold": 0.05,
            "discharge_price_threshold": 0.15,
            "charge_window_start": 22,
            "charge_window_end": 6,
            "discharge_allowed": True,
        }

    @pytest.fixture
    def planner(self, planner_options) -> EnergyPlanner:
        """Create planner instance."""
        return EnergyPlanner(planner_options)

    @pytest.fixture
    def sample_prices(self) -> PriceData:
        """Create sample price data."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # Create realistic Czech price pattern
        prices = [
            0.02, 0.02, 0.01, 0.01, 0.02, 0.03,  # 0-5 (night - lowest)
            0.05, 0.08, 0.10, 0.08, 0.07, 0.06,  # 6-11 (morning peak)
            0.05, 0.04, 0.04, 0.05, 0.06, 0.12,  # 12-17 (afternoon)
            0.15, 0.14, 0.10, 0.08, 0.06, 0.04,  # 18-23 (evening peak)
        ]
        today_prices = [
            HourlyPrice(start=today + timedelta(hours=h), price=p)
            for h, p in enumerate(prices)
        ]
        return PriceData(
            today=today_prices,
            tomorrow=[],
            current_price=prices[datetime.now().hour],
            tomorrow_available=False,
        )

    @pytest.fixture
    def sample_weather(self) -> WeatherForecast:
        """Create sample weather forecast."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        conditions = (
            ["cloudy"] * 6 +  # Night
            ["partly_cloudy"] * 2 +  # Early morning
            ["sunny"] * 8 +  # Day
            ["partly_cloudy"] * 2 +  # Late afternoon
            ["cloudy"] * 6  # Evening/night
        )
        hourly = [
            {
                "datetime": today + timedelta(hours=i),
                "condition": cond,
                "temperature": 20 + (5 if 10 <= i <= 16 else 0),
            }
            for i, cond in enumerate(conditions)
        ]
        return WeatherForecast(hourly=hourly)

    def test_planner_initialization(self, planner, planner_options) -> None:
        """Planner initializes with correct options."""
        assert planner.battery_capacity == planner_options["battery_capacity"]
        assert planner.max_pv_power == planner_options["max_pv_power"]
        assert planner.min_soc == planner_options["min_soc"]
        assert planner.max_soc == planner_options["max_soc"]

    def test_forecast_pv_generation_night(self, planner, sample_weather) -> None:
        """PV generation is zero at night."""
        night_hour = datetime.now().replace(hour=2, minute=0, second=0, microsecond=0)
        pv_wh, solar_potential, condition = planner.forecast_pv_generation(
            night_hour, sample_weather
        )
        assert pv_wh == 0.0
        assert solar_potential == 0.0
        assert condition == "night"

    def test_forecast_pv_generation_sunny_noon(self, planner, sample_weather) -> None:
        """PV generation is high at sunny noon."""
        noon = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        pv_wh, solar_potential, condition = planner.forecast_pv_generation(
            noon, sample_weather
        )
        # At noon with sunny weather, should be near peak
        assert pv_wh > 5000  # More than half of max
        assert solar_potential == 1.0
        assert condition == "sunny"

    def test_forecast_pv_generation_cloudy(self, planner) -> None:
        """PV generation is reduced on cloudy days."""
        noon = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        cloudy_weather = WeatherForecast(
            hourly=[{"datetime": noon, "condition": "cloudy", "temperature": 20}]
        )
        pv_wh, solar_potential, condition = planner.forecast_pv_generation(
            noon, cloudy_weather
        )
        # Cloudy reduces solar potential to 0.25
        assert solar_potential == 0.25
        assert pv_wh < 3000  # Much less than max

    def test_forecast_house_load_weekday_pattern(self, planner) -> None:
        """House load follows weekday pattern."""
        # Monday at 7am (morning peak)
        monday_morning = datetime(2025, 2, 3, 7, 0, 0)  # Monday
        load_morning = planner.forecast_house_load(monday_morning)
        
        # Monday at 3am (night low)
        monday_night = datetime(2025, 2, 3, 3, 0, 0)
        load_night = planner.forecast_house_load(monday_night)
        
        # Morning load should be higher than night
        assert load_morning > load_night

    def test_forecast_house_load_weekend_pattern(self, planner) -> None:
        """House load follows weekend pattern."""
        # Saturday at 10am (morning activity)
        saturday_morning = datetime(2025, 2, 1, 10, 0, 0)  # Saturday
        load = planner.forecast_house_load(saturday_morning)

        # Should be around average * 1.1
        assert 500 < load < 700

    def test_forecast_house_load_uses_historical_when_available(
        self, planner
    ) -> None:
        """House load uses historical average when provided for that slot."""
        # Monday 7am -> historical 700 Wh
        historical = {(7, 0): 700.0}  # (hour_of_day, weekday)
        monday_7am = datetime(2025, 2, 3, 7, 0, 0)  # Monday
        load = planner.forecast_house_load(monday_7am, historical_avg_wh=historical)
        assert load == 700.0

        # Missing slot falls back to pattern
        saturday_10am = datetime(2025, 2, 1, 10, 0, 0)  # Saturday
        load_fallback = planner.forecast_house_load(
            saturday_10am, historical_avg_wh=historical
        )
        assert load_fallback != 700.0
        assert 400 < load_fallback < 700

    def test_forecast_house_load_fallback_without_history(self, planner) -> None:
        """House load uses pattern when no historical profile given."""
        monday_7am = datetime(2025, 2, 3, 7, 0, 0)
        load_without = planner.forecast_house_load(monday_7am)
        load_with_none = planner.forecast_house_load(monday_7am, historical_avg_wh=None)
        assert load_without == load_with_none
        assert load_without > 0

    def test_create_plan_uses_historical_load_when_available(
        self, planner, sample_prices, sample_weather
    ) -> None:
        """create_plan uses historical load profile when plan_history provided."""
        history = PlanHistory()
        # Monday 2 Feb 2025 02:00 -> plan will include Monday 12:00 and 13:00
        monday_2am = datetime(2025, 2, 3, 2, 0, 0)  # Monday
        monday_12 = datetime(2025, 2, 3, 12, 0, 0)
        monday_13 = datetime(2025, 2, 3, 13, 0, 0)
        for h, load_wh in [(monday_12, 800.0), (monday_13, 600.0)]:
            history.add_comparison(
                PredictionComparison(
                    hour=h,
                    predicted=None,
                    actual=HourlyActual(
                        hour=h,
                        action_taken=None,
                        pv_actual_wh=None,
                        load_actual_wh=load_wh,
                        grid_import_actual_wh=None,
                        grid_export_actual_wh=None,
                        battery_soc_end=None,
                        price_actual=None,
                    ),
                )
            )
        plan = planner.create_plan(
            current_time=monday_2am,
            current_soc=50.0,
            prices=sample_prices,
            weather=sample_weather,
            plan_history=history,
        )
        assert plan is not None
        for entry in plan.entries:
            if entry.hour.hour == 12 and entry.hour.weekday() == 0:
                assert entry.load_forecast_wh == 800.0
            elif entry.hour.hour == 13 and entry.hour.weekday() == 0:
                assert entry.load_forecast_wh == 600.0
                break

    def test_create_plan_generates_entries(
        self, planner, sample_prices, sample_weather
    ) -> None:
        """create_plan generates plan with entries."""
        current_time = datetime.now()
        current_soc = 50.0

        plan = planner.create_plan(
            current_time=current_time,
            current_soc=current_soc,
            prices=sample_prices,
            weather=sample_weather,
        )

        assert plan is not None
        assert len(plan.entries) == 24  # 24 hours without tomorrow prices
        assert plan.created_at is not None

    def test_create_plan_with_tomorrow_prices(
        self, planner, sample_prices, sample_weather
    ) -> None:
        """create_plan extends horizon when tomorrow prices available."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        # Add tomorrow prices
        tomorrow_prices = [
            HourlyPrice(start=tomorrow + timedelta(hours=h), price=0.05)
            for h in range(24)
        ]
        sample_prices.tomorrow = tomorrow_prices
        sample_prices.tomorrow_available = True
        
        plan = planner.create_plan(
            current_time=datetime.now(),
            current_soc=50.0,
            prices=sample_prices,
            weather=sample_weather,
        )
        
        assert len(plan.entries) == 48  # Full 48 hours

    def test_create_plan_charges_during_cheap_hours(
        self, planner, sample_prices, sample_weather
    ) -> None:
        """Plan includes charging during cheap price hours in charge window."""
        # Set time to 23:00 (in charge window, cheap price at 0.04)
        current_time = datetime.now().replace(
            hour=23, minute=0, second=0, microsecond=0
        )
        
        plan = planner.create_plan(
            current_time=current_time,
            current_soc=50.0,  # Not full
            prices=sample_prices,
            weather=sample_weather,
        )
        
        # First entry should be charge if price is cheap
        first_entry = plan.entries[0]
        if first_entry.price and first_entry.price <= 0.05:
            assert first_entry.action == PlannedAction.CHARGE

    def test_create_plan_discharges_during_expensive_hours(
        self, planner, sample_prices, sample_weather
    ) -> None:
        """Plan includes discharging during expensive price hours."""
        # Set time to 18:00 (expensive price at 0.15)
        current_time = datetime.now().replace(
            hour=18, minute=0, second=0, microsecond=0
        )
        
        plan = planner.create_plan(
            current_time=current_time,
            current_soc=80.0,  # Plenty of charge
            prices=sample_prices,
            weather=sample_weather,
        )
        
        # First entry should be discharge if price is expensive
        first_entry = plan.entries[0]
        if first_entry.price and first_entry.price >= 0.15:
            assert first_entry.action == PlannedAction.DISCHARGE

    def test_create_plan_calculates_totals(
        self, planner, sample_prices, sample_weather
    ) -> None:
        """Plan calculates correct totals."""
        plan = planner.create_plan(
            current_time=datetime.now(),
            current_soc=50.0,
            prices=sample_prices,
            weather=sample_weather,
        )
        
        # Totals should be sum of entries
        assert plan.total_pv_forecast_wh == sum(e.pv_forecast_wh for e in plan.entries)
        assert plan.total_load_forecast_wh == sum(e.load_forecast_wh for e in plan.entries)
        assert plan.total_grid_import_wh >= 0
        assert plan.total_grid_export_wh >= 0

    def test_create_plan_soc_stays_in_bounds(
        self, planner, sample_prices, sample_weather
    ) -> None:
        """Predicted SOC stays within min/max bounds."""
        plan = planner.create_plan(
            current_time=datetime.now(),
            current_soc=50.0,
            prices=sample_prices,
            weather=sample_weather,
        )
        
        for entry in plan.entries:
            assert entry.predicted_soc >= planner.min_soc
            assert entry.predicted_soc <= planner.max_soc


class TestHourlyPlanEntry:
    """Test HourlyPlanEntry model."""

    def test_to_dict(self) -> None:
        """to_dict returns correct structure."""
        hour = datetime(2025, 2, 1, 12, 0, 0)
        entry = HourlyPlanEntry(
            hour=hour,
            action=PlannedAction.CHARGE,
            pv_forecast_wh=5000.0,
            load_forecast_wh=500.0,
            price=0.05,
            planned_grid_import_wh=3000.0,
            planned_grid_export_wh=0.0,
            planned_battery_charge_wh=2850.0,
            planned_battery_discharge_wh=0.0,
            predicted_soc=70.0,
            solar_potential=1.0,
            weather_condition="sunny",
            reason="Cheap price in charge window",
        )
        
        d = entry.to_dict()
        
        assert d["hour"] == hour.isoformat()
        assert d["action"] == "charge"
        assert d["pv_forecast_wh"] == 5000.0
        assert d["price"] == 0.05


class TestEnergyPlan:
    """Test EnergyPlan model."""

    @pytest.fixture
    def sample_plan(self) -> EnergyPlan:
        """Create sample energy plan."""
        hour_base = datetime(2025, 2, 1, 0, 0, 0)
        entries = []
        for i in range(24):
            entries.append(
                HourlyPlanEntry(
                    hour=hour_base + timedelta(hours=i),
                    action=PlannedAction.CHARGE if i < 6 else PlannedAction.SELF_USE,
                    pv_forecast_wh=500.0 * (1 if 6 <= i <= 18 else 0),
                    load_forecast_wh=500.0,
                    price=0.05 if i < 6 else 0.10,
                    planned_grid_import_wh=500.0,
                    planned_grid_export_wh=0.0,
                    planned_battery_charge_wh=0.0,
                    planned_battery_discharge_wh=0.0,
                    predicted_soc=50.0,
                    solar_potential=0.5,
                    weather_condition="cloudy",
                    reason="Test",
                )
            )
        return EnergyPlan(
            created_at=hour_base,
            entries=entries,
            total_pv_forecast_wh=6500.0,
            total_load_forecast_wh=12000.0,
        )

    def test_get_entry_at(self, sample_plan) -> None:
        """get_entry_at returns correct entry."""
        test_time = datetime(2025, 2, 1, 5, 30, 0)  # 5:30 AM
        entry = sample_plan.get_entry_at(test_time)
        
        assert entry is not None
        assert entry.hour.hour == 5

    def test_get_next_charge_hours(self, sample_plan) -> None:
        """get_next_charge_hours returns charge entries."""
        charge_hours = sample_plan.get_next_charge_hours(3)
        
        assert len(charge_hours) == 3
        for entry in charge_hours:
            assert entry.action == PlannedAction.CHARGE

    def test_to_dict(self, sample_plan) -> None:
        """to_dict returns correct structure."""
        d = sample_plan.to_dict()
        
        assert "created_at" in d
        assert "entries" in d
        assert len(d["entries"]) == 24


def test_build_historical_load_profile() -> None:
    """_build_historical_load_profile averages load_actual_wh per (hour, weekday)."""
    history = PlanHistory()
    # Monday 12:00 with 400 and 600 -> avg 500
    history.add_comparison(
        PredictionComparison(
            hour=datetime(2025, 2, 3, 12, 0, 0),
            predicted=None,
            actual=HourlyActual(
                hour=datetime(2025, 2, 3, 12, 0, 0),
                action_taken=None,
                pv_actual_wh=None,
                load_actual_wh=400.0,
                grid_import_actual_wh=None,
                grid_export_actual_wh=None,
                battery_soc_end=None,
                price_actual=None,
            ),
        )
    )
    history.add_comparison(
        PredictionComparison(
            hour=datetime(2025, 2, 10, 12, 0, 0),
            predicted=None,
            actual=HourlyActual(
                hour=datetime(2025, 2, 10, 12, 0, 0),
                action_taken=None,
                pv_actual_wh=None,
                load_actual_wh=600.0,
                grid_import_actual_wh=None,
                grid_export_actual_wh=None,
                battery_soc_end=None,
                price_actual=None,
            ),
        )
    )
    profile = _build_historical_load_profile(history)
    assert (12, 0) in profile  # Monday = 0
    assert profile[(12, 0)] == 500.0


class TestPlanHistory:
    """Test PlanHistory model."""

    @pytest.fixture
    def sample_history(self) -> PlanHistory:
        """Create sample plan history."""
        history = PlanHistory()
        hour_base = datetime(2025, 2, 1, 0, 0, 0)
        
        for i in range(24):
            hour = hour_base + timedelta(hours=i)
            predicted = HourlyPlanEntry(
                hour=hour,
                action=PlannedAction.SELF_USE,
                pv_forecast_wh=500.0,
                load_forecast_wh=500.0,
                price=0.10,
                planned_grid_import_wh=100.0,
                planned_grid_export_wh=0.0,
                planned_battery_charge_wh=0.0,
                planned_battery_discharge_wh=0.0,
                predicted_soc=50.0,
                solar_potential=0.5,
                weather_condition="cloudy",
                reason="Test",
            )
            actual = HourlyActual(
                hour=hour,
                action_taken=PlannedAction.SELF_USE,
                pv_actual_wh=480.0 + i * 2,  # Slight variation
                load_actual_wh=510.0,
                grid_import_actual_wh=110.0,
                grid_export_actual_wh=0.0,
                battery_soc_end=51.0,
                price_actual=0.10,
            )
            history.add_comparison(
                PredictionComparison(hour=hour, predicted=predicted, actual=actual)
            )
        
        return history

    def test_add_comparison_limits_entries(self) -> None:
        """add_comparison limits to max_entries."""
        history = PlanHistory(max_entries=10)
        hour_base = datetime(2025, 2, 1, 0, 0, 0)
        
        for i in range(20):
            comparison = PredictionComparison(
                hour=hour_base + timedelta(hours=i),
                predicted=None,
                actual=None,
            )
            history.add_comparison(comparison)
        
        assert len(history.comparisons) == 10

    def test_get_recent(self, sample_history) -> None:
        """get_recent returns correct number of entries."""
        recent = sample_history.get_recent(6)
        
        assert len(recent) == 6

    def test_pv_forecast_accuracy(self, sample_history) -> None:
        """pv_forecast_accuracy calculates correctly."""
        accuracy = sample_history.pv_forecast_accuracy
        
        assert accuracy is not None
        assert 90 <= accuracy <= 100  # Should be high given small errors

    def test_to_dict(self, sample_history) -> None:
        """to_dict returns correct structure."""
        d = sample_history.to_dict()
        
        assert "comparisons" in d
        assert "pv_forecast_accuracy" in d
        assert "load_forecast_accuracy" in d


class TestPredictionComparison:
    """Test PredictionComparison model."""

    def test_pv_error_calculation(self) -> None:
        """pv_error_wh calculates correctly."""
        hour = datetime(2025, 2, 1, 12, 0, 0)
        predicted = HourlyPlanEntry(
            hour=hour,
            action=PlannedAction.SELF_USE,
            pv_forecast_wh=500.0,
            load_forecast_wh=500.0,
            price=0.10,
            planned_grid_import_wh=0.0,
            planned_grid_export_wh=0.0,
            planned_battery_charge_wh=0.0,
            planned_battery_discharge_wh=0.0,
            predicted_soc=50.0,
            solar_potential=0.5,
            weather_condition="cloudy",
            reason="Test",
        )
        actual = HourlyActual(
            hour=hour,
            action_taken=PlannedAction.SELF_USE,
            pv_actual_wh=550.0,
            load_actual_wh=480.0,
            grid_import_actual_wh=0.0,
            grid_export_actual_wh=0.0,
            battery_soc_end=52.0,
            price_actual=0.10,
        )
        comparison = PredictionComparison(
            hour=hour, predicted=predicted, actual=actual
        )
        
        assert comparison.pv_error_wh == 50.0  # 550 - 500
        assert comparison.load_error_wh == -20.0  # 480 - 500
        assert comparison.soc_error_pct == 2.0  # 52 - 50


class TestRecordActualHour:
    """Test record_actual_hour function."""

    def test_records_comparison(self) -> None:
        """record_actual_hour adds comparison to history."""
        history = PlanHistory()
        hour = datetime(2025, 2, 1, 12, 0, 0)
        
        # Create a simple plan
        plan = EnergyPlan(
            created_at=hour,
            entries=[
                HourlyPlanEntry(
                    hour=hour,
                    action=PlannedAction.SELF_USE,
                    pv_forecast_wh=500.0,
                    load_forecast_wh=500.0,
                    price=0.10,
                    planned_grid_import_wh=0.0,
                    planned_grid_export_wh=0.0,
                    planned_battery_charge_wh=0.0,
                    planned_battery_discharge_wh=0.0,
                    predicted_soc=50.0,
                    solar_potential=0.5,
                    weather_condition="cloudy",
                    reason="Test",
                )
            ],
        )
        
        solax_state = SolaxState(
            battery_soc=52.0,
            current_mode="Self Use",
            active_power=0.0,
        )
        
        record_actual_hour(
            plan_history=history,
            energy_plan=plan,
            hour=hour,
            solax_state=solax_state,
            price=0.10,
        )
        
        assert len(history.comparisons) == 1
        assert history.comparisons[0].hour == hour
        assert history.comparisons[0].predicted is not None
        assert history.comparisons[0].actual is not None
