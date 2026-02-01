"""Integration tests for Solar Mind with Solax PV Simulator.

These tests simulate a complete scenario where Solar Mind controls
the simulated Solax inverter based on price data.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from solax_pv_simulator.simulator_core import SolaxSimulatorCore
from solax_pv_simulator.const import RemoteControlMode, SimulatedWeather
from solar_mind.models import (
    HourlyPrice,
    PriceData,
    SolaxState,
    StrategyInput,
    WeatherForecast,
)
from solar_mind.strategies.spot_price import SpotPriceWeatherStrategy
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
    SOLAX_MODE_GRID_CONTROL,
    SOLAX_MODE_SELF_USE,
)


class TestIntegrationScenarios:
    """Integration tests simulating complete scenarios."""

    @pytest.fixture
    def simulator(self, simulator_config_entry_mock):
        """Create a simulator instance."""
        return SolaxSimulatorCore(simulator_config_entry_mock.data)

    @pytest.fixture
    def strategy(self):
        """Create a spot price strategy."""
        return SpotPriceWeatherStrategy()

    @pytest.fixture
    def default_options(self):
        """Default strategy options."""
        return {
            CONF_CHARGE_PRICE_THRESHOLD: 0.05,
            CONF_DISCHARGE_PRICE_THRESHOLD: 0.15,
            CONF_CHARGE_WINDOW_START: 22,
            CONF_CHARGE_WINDOW_END: 6,
            CONF_DISCHARGE_ALLOWED: True,
            CONF_MIN_SOC: 10,
            CONF_MAX_SOC: 95,
            CONF_MAX_CHARGE_POWER: 3000,
            CONF_MAX_DISCHARGE_POWER: 3000,
        }

    def _create_price_data(self, current_hour: int) -> PriceData:
        """Create realistic Czech spot price data."""
        base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Czech-style prices: low at night, peak morning and evening
        prices = [
            0.02, 0.02, 0.01, 0.01, 0.02, 0.03,  # 0-5 (night)
            0.05, 0.08, 0.10, 0.08, 0.07, 0.06,  # 6-11 (morning)
            0.05, 0.04, 0.04, 0.05, 0.06, 0.12,  # 12-17 (afternoon)
            0.18, 0.16, 0.12, 0.08, 0.06, 0.04,  # 18-23 (evening peak)
        ]
        
        today_prices = [
            HourlyPrice(start=base + timedelta(hours=i), price=p)
            for i, p in enumerate(prices)
        ]
        
        return PriceData(
            today=today_prices,
            current_price=prices[current_hour],
        )

    def _create_strategy_input(
        self,
        hour: int,
        battery_soc: float,
        weather: list[dict] | None = None,
    ) -> StrategyInput:
        """Create strategy input for given conditions."""
        now = datetime.now().replace(hour=hour, minute=30, second=0, microsecond=0)
        
        return StrategyInput(
            current_time=now,
            prices=self._create_price_data(hour),
            weather=WeatherForecast(hourly=weather or []),
            solax_state=SolaxState(battery_soc=battery_soc),
        )

    def test_scenario_night_charging(self, simulator, strategy, default_options):
        """
        Scenario: Night charging with low prices
        
        At 3 AM when prices are low (0.01 CZK/kWh) and battery is at 30%,
        the system should charge the battery from the grid.
        """
        # Setup simulator
        simulator.set_simulated_hour(3)
        simulator.set_battery_soc(30)
        
        # Create strategy input
        input_data = self._create_strategy_input(hour=3, battery_soc=30)
        
        # Compute strategy
        result = strategy.compute(input_data, default_options)
        
        # Verify strategy recommends charging
        assert result.status == SystemStatus.CHARGING
        assert result.power_w is not None
        assert result.power_w > 0
        
        # Apply to simulator
        simulator.set_remote_control_mode(result.mode)
        simulator.set_active_power(result.power_w)
        simulator.trigger_remote_control()
        
        # Verify simulator is in correct mode
        assert simulator.state.remote_control_active is True
        assert simulator.state.remote_control_mode == RemoteControlMode.GRID_CONTROL

    def test_scenario_daytime_self_use(self, simulator, strategy, default_options):
        """
        Scenario: Daytime self-use with PV production
        
        At noon with sunny weather and battery at 60%, the system should
        use self-use mode to maximize PV utilization.
        """
        # Setup simulator
        simulator.set_simulated_hour(12)
        simulator.set_weather(SimulatedWeather.SUNNY)
        simulator.set_battery_soc(60)
        
        # Create strategy input with sunny forecast
        weather = [
            {
                "datetime": datetime.now().replace(hour=h, minute=0),
                "condition": "sunny",
            }
            for h in range(24)
        ]
        input_data = self._create_strategy_input(
            hour=12, battery_soc=60, weather=weather
        )
        
        # Compute strategy
        result = strategy.compute(input_data, default_options)
        
        # Should recommend self-use or house from grid
        assert result.status in (SystemStatus.SELF_USE, SystemStatus.HOUSE_FROM_GRID)

    def test_scenario_evening_peak_discharge(self, simulator, strategy, default_options):
        """
        Scenario: Evening peak with high prices
        
        At 6 PM when prices are high (0.18 CZK/kWh) and battery is at 80%,
        the system should discharge to the grid if allowed.
        """
        # Setup simulator
        simulator.set_simulated_hour(18)
        simulator.set_battery_soc(80)
        
        # Create strategy input
        input_data = self._create_strategy_input(hour=18, battery_soc=80)
        
        # Compute strategy (discharge allowed)
        result = strategy.compute(input_data, default_options)
        
        # Should recommend discharging
        assert result.status == SystemStatus.DISCHARGING
        
        # Apply to simulator
        simulator.set_remote_control_mode(result.mode)
        simulator.set_active_power(result.power_w or -3000)
        simulator.trigger_remote_control()
        
        # Verify simulator state
        assert simulator.state.remote_control_active is True

    def test_scenario_full_day_cycle(self, simulator, strategy, default_options):
        """
        Scenario: Complete 24-hour cycle
        
        Simulate a full day and verify the strategy makes appropriate
        decisions at different times.
        """
        results = {}
        
        # Test key hours
        test_hours = [
            (3, 30, "night_low"),      # Night, low price, low SOC
            (7, 50, "morning_peak"),   # Morning peak
            (12, 70, "midday_solar"),  # Midday, high solar potential
            (15, 60, "afternoon"),     # Afternoon
            (18, 80, "evening_peak"),  # Evening peak price
            (22, 40, "night_start"),   # Start of night tariff
        ]
        
        for hour, soc, label in test_hours:
            simulator.set_simulated_hour(hour)
            simulator.set_battery_soc(soc)
            
            input_data = self._create_strategy_input(hour=hour, battery_soc=soc)
            result = strategy.compute(input_data, default_options)
            
            results[label] = result
        
        # Verify expected behavior at key times
        assert results["night_low"].status == SystemStatus.CHARGING
        assert results["evening_peak"].status == SystemStatus.DISCHARGING
        # Midday should not be charging from grid
        assert results["midday_solar"].status != SystemStatus.CHARGING

    def test_scenario_battery_protection(self, simulator, strategy, default_options):
        """
        Scenario: Battery SOC protection
        
        Even with optimal prices, the system should respect battery limits.
        """
        # Test high SOC protection
        simulator.set_battery_soc(96)  # Above max_soc of 95
        input_data = self._create_strategy_input(hour=3, battery_soc=96)
        result = strategy.compute(input_data, default_options)
        
        # Should not charge when battery is full
        assert result.status != SystemStatus.CHARGING
        
        # Test low SOC protection
        simulator.set_battery_soc(8)  # Below min_soc of 10
        input_data = self._create_strategy_input(hour=18, battery_soc=8)
        result = strategy.compute(input_data, default_options)
        
        # Should not discharge when battery is low
        assert result.status != SystemStatus.DISCHARGING


class TestSimulatorEntityMapping:
    """Test that simulator entities can be used with Solar Mind config."""

    @pytest.fixture
    def simulator(self, simulator_config_entry_mock):
        """Create a simulator instance."""
        return SolaxSimulatorCore(simulator_config_entry_mock.data)

    def test_remote_control_flow(self, simulator):
        """Test the complete remote control flow matches Solar Mind expectations."""
        # Solar Mind would:
        # 1. Set mode via select entity
        simulator.set_remote_control_mode("Enabled Grid Control")
        
        # 2. Set power via number entity
        simulator.set_active_power(3000)
        
        # 3. Set duration via number entity
        simulator.set_autorepeat_duration(3600)
        
        # 4. Press trigger button
        simulator.trigger_remote_control()
        
        # Verify state
        assert simulator.state.remote_control_mode == RemoteControlMode.GRID_CONTROL
        assert simulator.state.active_power_setpoint == 3000
        assert simulator.state.autorepeat_duration == 3600
        assert simulator.state.remote_control_active is True

    def test_passive_mode_flow(self, simulator):
        """Test passive mode flow for Sofar inverters."""
        # Solar Mind would:
        # 1. Set desired grid power
        simulator.set_passive_grid_power(2500)
        
        # 2. Press passive update button
        simulator.trigger_passive_update()
        
        # Verify state
        assert simulator.state.passive_grid_power == 2500
        assert simulator.state.remote_control_active is True

    def test_sensor_readings(self, simulator):
        """Test sensor values are accessible."""
        # Set known state
        simulator.set_battery_soc(65)
        simulator.set_house_load(1500)
        simulator.set_simulated_hour(12)
        simulator.set_weather(SimulatedWeather.SUNNY)
        
        # Update PV production
        simulator._update_pv_production()
        
        # Verify readable values
        assert simulator.state.battery_soc == 65
        assert simulator.state.house_load == 1500
        assert simulator.state.pv_power > 0  # Should be producing at noon
        assert simulator.state.grid_voltage == 230.0
        assert simulator.state.grid_frequency == 50.0
