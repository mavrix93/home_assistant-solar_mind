"""Tests for Solar Mind strategies."""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root and custom_components so solar_mind can be imported (after HA mock in conftest)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "custom_components") not in sys.path:
    sys.path.insert(0, str(ROOT / "custom_components"))

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from solar_mind.strategies.spot_price import SpotPriceWeatherStrategy
from solar_mind.strategies.time_of_use import TimeOfUseStrategy
from solar_mind.strategies.self_use_only import SelfUseOnlyStrategy
from solar_mind.strategies.manual import ManualStrategy
from solar_mind.models import (
    HourlyPrice,
    PriceData,
    SolaxState,
    StrategyInput,
    WeatherForecast,
)
from solar_mind.const import (
    CONF_CHARGE_PRICE_THRESHOLD,
    CONF_DISCHARGE_PRICE_THRESHOLD,
    CONF_CHARGE_WINDOW_START,
    CONF_CHARGE_WINDOW_END,
    CONF_DISCHARGE_ALLOWED,
    CONF_MIN_SOC,
    CONF_MAX_SOC,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    SystemStatus,
)


class TestSpotPriceStrategy:
    """Test the spot price strategy."""

    @pytest.fixture
    def strategy(self):
        """Create a spot price strategy instance."""
        return SpotPriceWeatherStrategy()

    @pytest.fixture
    def default_options(self):
        """Create default options."""
        return {
            CONF_CHARGE_PRICE_THRESHOLD: 0.05,
            CONF_DISCHARGE_PRICE_THRESHOLD: 0.15,
            CONF_CHARGE_WINDOW_START: 22,
            CONF_CHARGE_WINDOW_END: 6,
            CONF_DISCHARGE_ALLOWED: False,
            CONF_MIN_SOC: 10,
            CONF_MAX_SOC: 95,
            CONF_MAX_CHARGE_POWER: 3000,
            CONF_MAX_DISCHARGE_POWER: 3000,
        }

    @pytest.fixture
    def make_strategy_input(self, make_hourly_prices, make_weather_forecast):
        """Factory to create strategy input."""
        def _make_input(
            hour: int = 12,
            current_price: float = 0.08,
            battery_soc: float = 50.0,
            prices: list[float] | None = None,
        ) -> StrategyInput:
            now = datetime.now().replace(hour=hour, minute=30, second=0, microsecond=0)
            base_date = now.replace(hour=0, minute=0)
            
            hourly_prices = make_hourly_prices(base_date, prices)
            price_data = PriceData(
                today=[HourlyPrice(start=p["start"], price=p["price"]) for p in hourly_prices],
                tomorrow=[],
                current_price=current_price,
                tomorrow_available=False,
            )
            
            weather_data = WeatherForecast(
                hourly=make_weather_forecast(base_date),
                daily=[],
            )
            
            solax_state = SolaxState(
                battery_soc=battery_soc,
                current_mode="Enabled Self Use",
            )
            
            return StrategyInput(
                current_time=now,
                prices=price_data,
                weather=weather_data,
                solax_state=solax_state,
                options={},
            )
        
        return _make_input

    def test_strategy_key_and_name(self, strategy):
        """Test strategy has correct key and name."""
        assert strategy.key == "spot_price_weather"
        assert "Spot" in strategy.name or "spot" in strategy.name.lower()

    def test_charges_when_price_low_in_window(
        self, strategy, make_strategy_input, default_options
    ):
        """Test strategy recommends charging when price is low and in window."""
        # Night hour (in charge window 22-6)
        input_data = make_strategy_input(
            hour=3,  # 3 AM - in window
            current_price=0.02,  # Below threshold of 0.05
            battery_soc=40,  # Room to charge
        )
        
        result = strategy.compute(input_data, default_options)
        
        assert result.status == SystemStatus.CHARGING
        assert result.power_w is not None
        assert result.power_w > 0

    def test_no_charge_when_price_high(
        self, strategy, make_strategy_input, default_options
    ):
        """Test strategy does not charge when price is above threshold."""
        input_data = make_strategy_input(
            hour=3,  # In window
            current_price=0.10,  # Above threshold of 0.05
            battery_soc=40,
        )
        
        result = strategy.compute(input_data, default_options)
        
        # Should not be charging
        assert result.status != SystemStatus.CHARGING

    def test_no_charge_outside_window(
        self, strategy, make_strategy_input, default_options
    ):
        """Test strategy does not charge outside window even with low price."""
        input_data = make_strategy_input(
            hour=12,  # Noon - outside window (22-6)
            current_price=0.02,  # Low price
            battery_soc=40,
        )
        
        result = strategy.compute(input_data, default_options)
        
        # Should not be charging from grid outside window
        assert result.status != SystemStatus.CHARGING

    def test_no_charge_when_battery_full(
        self, strategy, make_strategy_input, default_options
    ):
        """Test strategy does not charge when battery is full."""
        input_data = make_strategy_input(
            hour=3,  # In window
            current_price=0.02,  # Low price
            battery_soc=96,  # Above max_soc of 95
        )
        
        result = strategy.compute(input_data, default_options)
        
        assert result.status != SystemStatus.CHARGING

    def test_discharges_when_allowed_and_price_high(
        self, strategy, make_strategy_input, default_options
    ):
        """Test strategy recommends discharge when allowed and price is high."""
        options = {**default_options, CONF_DISCHARGE_ALLOWED: True}
        
        input_data = make_strategy_input(
            hour=18,  # Evening
            current_price=0.20,  # Above discharge threshold of 0.15
            battery_soc=80,  # Has charge to discharge
        )
        
        result = strategy.compute(input_data, options)
        
        assert result.status == SystemStatus.DISCHARGING

    def test_no_discharge_when_not_allowed(
        self, strategy, make_strategy_input, default_options
    ):
        """Test strategy does not discharge when not allowed."""
        input_data = make_strategy_input(
            hour=18,
            current_price=0.20,  # High price
            battery_soc=80,
        )
        
        result = strategy.compute(input_data, default_options)
        
        # Discharge not allowed by default
        assert result.status != SystemStatus.DISCHARGING

    def test_self_use_during_day(
        self, strategy, make_strategy_input, default_options
    ):
        """Test strategy recommends self-use during day with moderate price."""
        input_data = make_strategy_input(
            hour=12,  # Midday
            current_price=0.08,  # Medium price
            battery_soc=60,
        )
        
        result = strategy.compute(input_data, default_options)
        
        # Should be self-use or house from grid during day
        assert result.status in (SystemStatus.SELF_USE, SystemStatus.HOUSE_FROM_GRID)


class TestTimeOfUseStrategy:
    """Test the time-of-use strategy."""

    @pytest.fixture
    def strategy(self):
        """Create a time-of-use strategy instance."""
        return TimeOfUseStrategy()

    @pytest.fixture
    def default_options(self):
        """Create default options."""
        return {
            CONF_CHARGE_WINDOW_START: 22,
            CONF_CHARGE_WINDOW_END: 6,
            CONF_MIN_SOC: 10,
            CONF_MAX_SOC: 95,
            CONF_MAX_CHARGE_POWER: 3000,
        }

    def test_strategy_key_and_name(self, strategy):
        """Test strategy has correct key and name."""
        assert strategy.key == "time_of_use"
        assert "Time" in strategy.name or "time" in strategy.name.lower()

    def test_charges_in_window(self, strategy, default_options):
        """Test charges during configured window."""
        now = datetime.now().replace(hour=3, minute=0)  # 3 AM - in window
        
        input_data = StrategyInput(
            current_time=now,
            prices=PriceData(),
            weather=WeatherForecast(),
            solax_state=SolaxState(battery_soc=50),
        )
        
        result = strategy.compute(input_data, default_options)
        
        assert result.status == SystemStatus.CHARGING

    def test_self_use_outside_window(self, strategy, default_options):
        """Test uses self-use mode outside window."""
        now = datetime.now().replace(hour=14, minute=0)  # 2 PM - outside window
        
        input_data = StrategyInput(
            current_time=now,
            prices=PriceData(),
            weather=WeatherForecast(),
            solax_state=SolaxState(battery_soc=50),
        )
        
        result = strategy.compute(input_data, default_options)
        
        assert result.status in (SystemStatus.SELF_USE, SystemStatus.HOUSE_FROM_GRID)


class TestSelfUseOnlyStrategy:
    """Test the self-use only strategy."""

    @pytest.fixture
    def strategy(self):
        """Create a self-use only strategy instance."""
        return SelfUseOnlyStrategy()

    def test_strategy_key_and_name(self, strategy):
        """Test strategy has correct key and name."""
        assert strategy.key == "self_use_only"

    def test_always_self_use(self, strategy):
        """Test always recommends self-use mode."""
        now = datetime.now()
        
        input_data = StrategyInput(
            current_time=now,
            prices=PriceData(),
            weather=WeatherForecast(),
            solax_state=SolaxState(battery_soc=50),
        )
        
        result = strategy.compute(input_data, {})
        
        assert result.status == SystemStatus.SELF_USE


class TestManualStrategy:
    """Test the manual strategy."""

    @pytest.fixture
    def strategy(self):
        """Create a manual strategy instance."""
        return ManualStrategy()

    def test_strategy_key_and_name(self, strategy):
        """Test strategy has correct key and name."""
        assert strategy.key == "manual"

    def test_returns_idle(self, strategy):
        """Test returns idle status (no automatic action)."""
        now = datetime.now()
        
        input_data = StrategyInput(
            current_time=now,
            prices=PriceData(),
            weather=WeatherForecast(),
            solax_state=SolaxState(battery_soc=50),
        )
        
        result = strategy.compute(input_data, {})
        
        assert result.status == SystemStatus.IDLE
