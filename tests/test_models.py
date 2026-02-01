"""Tests for Solar Mind data models."""
from __future__ import annotations

from datetime import datetime

import pytest

from custom_components.solar_mind.models import (
    HourlyPrice,
    PriceData,
    StrategyOutput,
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
