"""Tests for Solar Mind data models."""
from datetime import datetime, timezone

import pytest

from custom_components.solar_mind.models import (
    AwayPeriod,
    EventLog,
    EventSeverity,
    EventType,
    HourlyPrice,
    Milestone,
    PriceData,
    StrategyOutput,
    SystemEvent,
    SystemHealth,
    UserPreferences,
    WeatherForecast,
)
from custom_components.solar_mind.const import SystemStatus


class TestHourlyPrice:
    """Test HourlyPrice model."""

    def test_valid_creation(self) -> None:
        """Valid datetime and price creates HourlyPrice."""
        dt = datetime(2025, 2, 1, 12, 0, 0)
        hp = HourlyPrice(start=dt, price=0.05)
        assert hp.start == dt
        assert hp.price == 0.05

    def test_invalid_start_raises(self) -> None:
        """Non-datetime start raises ValueError."""
        with pytest.raises(ValueError, match="start must be a datetime"):
            HourlyPrice(start="2025-02-01", price=0.05)


class TestPriceData:
    """Test PriceData model."""

    def test_get_cheapest_hours(self) -> None:
        """get_cheapest_hours returns N cheapest hours."""
        today = datetime(2025, 2, 1, 0, 0, 0)
        prices = [
            HourlyPrice(start=today.replace(hour=h), price=float(10 - h % 5))
            for h in range(24)
        ]
        price_data = PriceData(today=prices)
        cheapest = price_data.get_cheapest_hours(3)
        assert len(cheapest) == 3
        sorted_prices = sorted(p.price for p in cheapest)
        assert sorted_prices == sorted(sorted_prices)

    def test_get_price_at(self) -> None:
        """get_price_at returns price for given datetime."""
        today = datetime(2025, 2, 1, 0, 0, 0)
        prices = [
            HourlyPrice(start=today.replace(hour=14), price=0.12),
        ]
        price_data = PriceData(today=prices)
        assert price_data.get_price_at(today.replace(hour=14, minute=30)) == 0.12
        assert price_data.get_price_at(today.replace(hour=15, minute=0)) is None


class TestWeatherForecast:
    """Test WeatherForecast model."""

    def test_get_solar_potential_default(self) -> None:
        """Empty forecast returns 0.5 default."""
        w = WeatherForecast()
        assert w.get_solar_potential(12) == 0.5

    def test_get_solar_potential_sunny(self) -> None:
        """Sunny condition returns 1.0."""
        w = WeatherForecast(
            hourly=[{"datetime": datetime(2025, 2, 1, 12, 0), "condition": "sunny"}]
        )
        assert w.get_solar_potential(12) == 1.0

    def test_get_solar_potential_cloudy(self) -> None:
        """Cloudy condition returns 0.3."""
        w = WeatherForecast(
            hourly=[{"datetime": datetime(2025, 2, 1, 12, 0), "condition": "cloudy"}]
        )
        assert w.get_solar_potential(12) == 0.3


class TestStrategyOutput:
    """Test StrategyOutput model."""

    def test_recommended_action_charging(self) -> None:
        """Charging status returns charge action string."""
        out = StrategyOutput(
            status=SystemStatus.CHARGING,
            mode="Enabled Grid Control",
            power_w=3000,
            reason="Cheap price",
        )
        assert "Charge" in out.recommended_action
        assert "3000" in out.recommended_action

    def test_recommended_action_self_use(self) -> None:
        """Self-use status returns self use string."""
        out = StrategyOutput(
            status=SystemStatus.SELF_USE,
            mode="Enabled Self Use",
            reason="Good solar",
        )
        assert "Self use" in out.recommended_action


class TestSystemEvent:
    """Test SystemEvent model."""

    def test_to_dict(self) -> None:
        """to_dict returns correct structure."""
        ts = datetime(2025, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
        event = SystemEvent(
            timestamp=ts,
            event_type=EventType.STRATEGY_CHANGED,
            severity=EventSeverity.INFO,
            title="Strategy changed",
            description="Switched to spot price",
            data={"strategy": "spot_price"},
        )
        d = event.to_dict()
        assert d["timestamp"] == ts.isoformat()
        assert d["event_type"] == "strategy_changed"
        assert d["severity"] == "info"
        assert d["title"] == "Strategy changed"
        assert d["data"] == {"strategy": "spot_price"}


class TestEventLog:
    """Test EventLog model."""

    def test_add_event_and_get_recent(self) -> None:
        """add_event and get_recent work correctly."""
        log = EventLog(max_events=5)
        ts = datetime(2025, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
        for i in range(7):
            log.add_event(
                SystemEvent(
                    timestamp=ts,
                    event_type=EventType.STRATEGY_CHANGED,
                    severity=EventSeverity.INFO,
                    title=f"Event {i}",
                    description="",
                )
            )
        assert len(log.events) == 5
        recent = log.get_recent(3)
        assert len(recent) == 3
        assert recent[0].title == "Event 6"

    def test_get_by_type(self) -> None:
        """get_by_type returns only matching events."""
        log = EventLog()
        ts = datetime(2025, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
        log.add_event(
            SystemEvent(ts, EventType.BATTERY_FULL, EventSeverity.SUCCESS, "Full", "")
        )
        log.add_event(
            SystemEvent(ts, EventType.STRATEGY_CHANGED, EventSeverity.INFO, "Changed", "")
        )
        log.add_event(
            SystemEvent(ts, EventType.BATTERY_FULL, EventSeverity.SUCCESS, "Full 2", "")
        )
        battery = log.get_by_type(EventType.BATTERY_FULL, 10)
        assert len(battery) == 2
        assert battery[0].title == "Full 2"

    def test_to_dict(self) -> None:
        """to_dict includes events and total_count."""
        log = EventLog()
        ts = datetime(2025, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
        log.add_event(
            SystemEvent(ts, EventType.PRICE_SPIKE, EventSeverity.WARNING, "Spike", "")
        )
        d = log.to_dict()
        assert "events" in d
        assert d["total_count"] == 1


class TestAwayPeriod:
    """Test AwayPeriod model."""

    def test_is_active(self) -> None:
        """is_active returns True only within start–end."""
        start = datetime(2025, 2, 1, 8, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 2, 3, 18, 0, 0, tzinfo=timezone.utc)
        period = AwayPeriod(id="ap1", start=start, end=end, label="Vacation")
        assert period.is_active(datetime(2025, 2, 2, 12, 0, 0, tzinfo=timezone.utc)) is True
        assert period.is_active(datetime(2025, 2, 1, 7, 0, 0, tzinfo=timezone.utc)) is False
        assert period.is_active(datetime(2025, 2, 3, 19, 0, 0, tzinfo=timezone.utc)) is False

    def test_to_dict(self) -> None:
        """to_dict returns correct structure."""
        start = datetime(2025, 2, 1, 8, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 2, 3, 18, 0, 0, tzinfo=timezone.utc)
        period = AwayPeriod(
            id="ap1", start=start, end=end, label="Trip", reduce_load_percent=70.0
        )
        d = period.to_dict()
        assert d["id"] == "ap1"
        assert d["label"] == "Trip"
        assert d["reduce_load_percent"] == 70.0


class TestUserPreferences:
    """Test UserPreferences model."""

    def test_get_active_away_period(self) -> None:
        """get_active_away_period returns period that contains given time."""
        start = datetime(2025, 2, 1, 8, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 2, 3, 18, 0, 0, tzinfo=timezone.utc)
        period = AwayPeriod(id="ap1", start=start, end=end, label="Vacation")
        prefs = UserPreferences(away_periods=[period])
        at_time = datetime(2025, 2, 2, 12, 0, 0, tzinfo=timezone.utc)
        assert prefs.get_active_away_period(at_time) is period
        assert prefs.get_active_away_period(datetime(2025, 2, 5, 12, 0, 0, tzinfo=timezone.utc)) is None

    def test_add_away_period_replaces_same_id(self) -> None:
        """add_away_period replaces existing period with same ID."""
        start = datetime(2025, 2, 1, 8, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 2, 3, 18, 0, 0, tzinfo=timezone.utc)
        p1 = AwayPeriod(id="ap1", start=start, end=end, label="First")
        p2 = AwayPeriod(id="ap1", start=start, end=end, label="Second")
        prefs = UserPreferences(away_periods=[p1])
        prefs.add_away_period(p2)
        assert len(prefs.away_periods) == 1
        assert prefs.away_periods[0].label == "Second"

    def test_remove_away_period(self) -> None:
        """remove_away_period removes by ID and returns True when found."""
        period = AwayPeriod(
            id="ap1",
            start=datetime(2025, 2, 1, 8, 0, 0, tzinfo=timezone.utc),
            end=datetime(2025, 2, 3, 18, 0, 0, tzinfo=timezone.utc),
        )
        prefs = UserPreferences(away_periods=[period])
        assert prefs.remove_away_period("ap1") is True
        assert len(prefs.away_periods) == 0
        assert prefs.remove_away_period("ap1") is False

    def test_high_demand_appliances(self) -> None:
        """high_demand_appliances dict is stored and serialized."""
        prefs = UserPreferences(high_demand_appliances={"Water heater": 2000.0})
        prefs.high_demand_appliances["Dishwasher"] = 1500.0
        d = prefs.to_dict()
        assert d["high_demand_appliances"]["Water heater"] == 2000.0
        assert d["high_demand_appliances"]["Dishwasher"] == 1500.0


class TestMilestone:
    """Test Milestone model."""

    def test_to_dict(self) -> None:
        """to_dict returns correct structure."""
        ts = datetime(2025, 2, 1, 14, 0, 0, tzinfo=timezone.utc)
        m = Milestone(
            timestamp=ts,
            milestone_type="surplus_start",
            title="Solar surplus",
            description="PV exceeds load",
            priority=1,
            data={"wh": 500},
        )
        d = m.to_dict()
        assert d["timestamp"] == ts.isoformat()
        assert d["milestone_type"] == "surplus_start"
        assert d["priority"] == 1
        assert d["data"] == {"wh": 500}


class TestSystemHealth:
    """Test SystemHealth model."""

    def test_health_score_starts_at_100(self) -> None:
        """health_score is 100 with no issues."""
        h = SystemHealth()
        assert h.health_score == 100.0

    def test_health_score_deductions(self) -> None:
        """health_score deducts for warnings and errors."""
        h = SystemHealth()
        h.add_warning("High temp")
        h.add_warning("Comm error")
        assert h.health_score == 90.0  # 100 - 2*5
        h.add_error("Failed")
        assert h.health_score <= 88.0

    def test_add_warning_no_duplicate(self) -> None:
        """add_warning does not add same warning twice."""
        h = SystemHealth()
        h.add_warning("Same")
        h.add_warning("Same")
        assert len(h.active_warnings) == 1

    def test_clear_warning(self) -> None:
        """clear_warning removes the warning."""
        h = SystemHealth()
        h.add_warning("Temp")
        h.clear_warning("Temp")
        assert "Temp" not in h.active_warnings

    def test_recent_errors_capped(self) -> None:
        """add_error keeps only last 50 errors."""
        h = SystemHealth()
        for i in range(60):
            h.add_error(f"Error {i}")
        assert len(h.recent_errors) == 50

    def test_to_dict_includes_health_score(self) -> None:
        """to_dict includes health_score."""
        h = SystemHealth(battery_temperature=30.0)
        d = h.to_dict()
        assert "health_score" in d
        assert d["battery_temperature"] == 30.0
