"""Tests for Solar Mind data models."""
from datetime import datetime, timezone

import pytest

from custom_components.solar_mind.mind.models import (
    HourlyPrice,
    PriceData,
    SolarMindData,
)
from custom_components.solar_mind.ha.const import (
    SystemStatus,
    StrategyOutput,
)


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

    def test_tomorrow_available(self) -> None:
        """Test tomorrow_available flag."""
        price_data = PriceData()
        assert price_data.tomorrow_available is False
        price_data.tomorrow_available = True
        assert price_data.tomorrow_available is True

    def test_current_price(self) -> None:
        """Test current_price attribute."""
        price_data = PriceData(current_price=1.23)
        assert price_data.current_price == 1.23


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

    def test_recommended_action_discharging(self) -> None:
        """Discharging status returns discharge action string."""
        out = StrategyOutput(
            status=SystemStatus.DISCHARGING,
            mode="Enabled Grid Control",
            power_w=-2000,
            reason="High price",
        )
        assert "Discharge" in out.recommended_action

    def test_recommended_action_house_from_grid(self) -> None:
        """House from grid status returns appropriate string."""
        out = StrategyOutput(
            status=SystemStatus.HOUSE_FROM_GRID,
            mode="Enabled No Discharge",
            reason="Preserve battery",
        )
        assert "House from grid" in out.recommended_action

    def test_recommended_action_idle(self) -> None:
        """Idle status returns idle string."""
        out = StrategyOutput(
            status=SystemStatus.IDLE,
            mode="",
            reason="Manual mode",
        )
        assert "Idle" in out.recommended_action


class TestSolarMindData:
    """Test SolarMindData model."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        data = SolarMindData()
        assert isinstance(data.prices, PriceData)
        assert data.price_mode == "spot"
        assert data.last_update is None
        assert data.last_error is None
        assert data.generation_forecast is None
        assert data.charge_to_soc_status == "Idle"
        assert data.charge_to_soc_target == 80
        assert data.charge_to_soc_active is False

    def test_with_values(self) -> None:
        """Test creation with custom values."""
        now = datetime.now(timezone.utc)
        data = SolarMindData(
            price_mode="fixed",
            last_update=now,
            charge_to_soc_target=90,
            charge_to_soc_active=True,
        )
        assert data.price_mode == "fixed"
        assert data.last_update == now
        assert data.charge_to_soc_target == 90
        assert data.charge_to_soc_active is True
