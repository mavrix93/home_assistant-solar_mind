"""Tests for the Solax PV Simulator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from solax_pv_simulator.simulator_core import SolaxSimulatorCore, SimulatorState
from solax_pv_simulator.const import (
    RemoteControlMode,
    EnergyStorageMode,
    SimulatedWeather,
    DEFAULT_BATTERY_CAPACITY,
)


class TestSimulatorState:
    """Test SimulatorState dataclass."""

    def test_default_values(self):
        """Test default state values."""
        state = SimulatorState()
        
        assert state.battery_soc == 50.0
        assert state.battery_power == 0.0
        assert state.pv_power == 0.0
        assert state.grid_power == 0.0
        assert state.house_load == 500.0
        assert state.remote_control_mode == RemoteControlMode.SELF_USE
        assert state.energy_storage_mode == EnergyStorageMode.SELF_USE
        assert state.weather == SimulatedWeather.SUNNY
        assert state.use_real_time is True

    def test_battery_capacity_default(self):
        """Test default battery capacity."""
        state = SimulatorState()
        assert state.battery_capacity == DEFAULT_BATTERY_CAPACITY


class TestSolaxSimulator:
    """Test SolaxSimulatorCore class (no HA deps)."""

    @pytest.fixture
    def simulator(self, simulator_config_entry_mock):
        """Create a simulator instance from config dict."""
        return SolaxSimulatorCore(simulator_config_entry_mock.data)

    def test_initialization(self, simulator, simulator_config_entry_mock):
        """Test simulator initializes with config values."""
        assert simulator.state.battery_capacity == 10000
        assert simulator.state.max_pv_power == 10000
        assert simulator.state.max_charge_power == 5000
        assert simulator.state.max_discharge_power == 5000
        assert simulator.state.battery_soc == 50

    def test_set_remote_control_mode(self, simulator):
        """Test setting remote control mode."""
        simulator.set_remote_control_mode(RemoteControlMode.GRID_CONTROL)
        assert simulator.state.remote_control_mode == RemoteControlMode.GRID_CONTROL

        simulator.set_remote_control_mode("Enabled Battery Control")
        assert simulator.state.remote_control_mode == RemoteControlMode.BATTERY_CONTROL

    def test_set_active_power(self, simulator):
        """Test setting active power setpoint."""
        simulator.set_active_power(3000)
        assert simulator.state.active_power_setpoint == 3000

        simulator.set_active_power(-2000)
        assert simulator.state.active_power_setpoint == -2000

    def test_set_autorepeat_duration(self, simulator):
        """Test setting autorepeat duration."""
        simulator.set_autorepeat_duration(1800)
        assert simulator.state.autorepeat_duration == 1800

    def test_trigger_remote_control(self, simulator):
        """Test triggering remote control."""
        simulator.set_remote_control_mode(RemoteControlMode.GRID_CONTROL)
        simulator.set_active_power(2500)
        simulator.set_autorepeat_duration(3600)
        
        simulator.trigger_remote_control()
        
        assert simulator.state.remote_control_active is True
        assert simulator.state.remote_control_expires is not None
        assert simulator.state.remote_control_expires > datetime.now(timezone.utc)

    def test_set_weather(self, simulator):
        """Test setting simulated weather."""
        simulator.set_weather(SimulatedWeather.CLOUDY)
        assert simulator.state.weather == SimulatedWeather.CLOUDY

        simulator.set_weather("rainy")
        assert simulator.state.weather == SimulatedWeather.RAINY

    def test_set_simulated_hour(self, simulator):
        """Test setting simulated hour."""
        simulator.set_simulated_hour(14)
        assert simulator.state.simulated_hour == 14
        assert simulator.state.use_real_time is False

        # Test wrapping
        simulator.set_simulated_hour(26)
        assert simulator.state.simulated_hour == 2

    def test_use_real_time(self, simulator):
        """Test enabling/disabling real-time mode."""
        simulator.set_simulated_hour(12)
        assert simulator.state.use_real_time is False

        simulator.use_real_time(True)
        assert simulator.state.use_real_time is True

    def test_set_battery_soc(self, simulator):
        """Test setting battery SOC directly."""
        simulator.set_battery_soc(75)
        assert simulator.state.battery_soc == 75
        # Energy should be updated too
        expected_energy = (75 / 100) * simulator.state.battery_capacity
        assert simulator.state.battery_energy == expected_energy

        # Test clamping
        simulator.set_battery_soc(150)
        assert simulator.state.battery_soc == 100

        simulator.set_battery_soc(-10)
        assert simulator.state.battery_soc == 0

    def test_set_house_load(self, simulator):
        """Test setting fixed house load."""
        simulator.set_house_load(2000)
        assert simulator.state.house_load == 2000

        # Test minimum
        simulator.set_house_load(-100)
        assert simulator.state.house_load == 0

    def test_add_remove_listener(self, simulator):
        """Test adding and removing state listeners."""
        callback_called = False

        def on_change():
            nonlocal callback_called
            callback_called = True

        remove = simulator.add_listener(on_change)
        assert on_change in simulator.state.listeners

        simulator._notify_listeners()
        assert callback_called

        remove()
        assert on_change not in simulator.state.listeners


class TestSimulatorPVProduction:
    """Test PV production simulation."""

    @pytest.fixture
    def simulator(self, simulator_config_entry_mock):
        """Create a simulator instance."""
        return SolaxSimulatorCore(simulator_config_entry_mock.data)

    def test_pv_production_at_noon(self, simulator):
        """Test PV production is highest at noon."""
        simulator.set_weather(SimulatedWeather.SUNNY)
        simulator.set_simulated_hour(12)
        
        simulator._update_pv_production()
        
        # At noon (summer solstice default) with sunny weather, PV should be high
        # (sun elevation ~88% at 51.5°N; variation ±4%)
        assert simulator.state.pv_power > simulator.state.max_pv_power * 0.80

    def test_pv_production_at_night(self, simulator):
        """Test PV production is zero at night."""
        simulator.set_simulated_hour(2)  # 2 AM
        
        simulator._update_pv_production()
        
        assert simulator.state.pv_power == 0

    def test_pv_production_with_clouds(self, simulator):
        """Test PV production is reduced with cloudy weather."""
        simulator.set_weather(SimulatedWeather.CLOUDY)
        simulator.set_simulated_hour(12)
        
        simulator._update_pv_production()
        
        # Cloudy should reduce to a small fraction of max (realistic winter/cloudy)
        assert simulator.state.pv_power < simulator.state.max_pv_power * 0.15

    def test_pv_production_at_sunrise(self, simulator):
        """Test PV production increases at sunrise."""
        simulator.set_weather(SimulatedWeather.SUNNY)
        
        # Just after sunrise (7 AM)
        simulator.set_simulated_hour(7)
        simulator._update_pv_production()
        pv_morning = simulator.state.pv_power
        
        # Midday (12 PM)
        simulator.set_simulated_hour(12)
        simulator._update_pv_production()
        pv_noon = simulator.state.pv_power
        
        assert pv_morning < pv_noon

    def test_pv_production_winter_lower_than_summer(self, simulator):
        """Test PV production is lower in winter than summer (same hour, latitude)."""
        simulator.set_weather(SimulatedWeather.SUNNY)
        simulator.set_simulated_hour(12)

        # Winter solstice noon
        winter_noon = datetime(2024, 12, 21, 12, 0)
        simulator._update_pv_production(winter_noon)
        pv_winter = simulator.state.pv_power

        # Summer solstice noon (default date in _update_pv_production when now passed)
        summer_noon = datetime(2024, 6, 21, 12, 0)
        simulator._update_pv_production(summer_noon)
        pv_summer = simulator.state.pv_power

        assert pv_winter > 0
        assert pv_summer > pv_winter

    def test_pv_production_cloudy_winter_very_low(self, simulator):
        """Test cloudy winter noon gives very low PV (realistic)."""
        simulator.set_weather(SimulatedWeather.CLOUDY)
        simulator.set_simulated_hour(12)
        winter_noon = datetime(2024, 12, 21, 12, 0)
        simulator._update_pv_production(winter_noon)
        # Winter noon ~26% sun elevation; cloudy 7% → ~1.8% of max before variation
        assert simulator.state.pv_power < simulator.state.max_pv_power * 0.05


class TestSimulatorPowerFlow:
    """Test power flow simulation."""

    @pytest.fixture
    def simulator(self, simulator_config_entry_mock):
        """Create a simulator instance."""
        sim = SolaxSimulatorCore(simulator_config_entry_mock.data)
        sim.set_simulated_hour(12)
        sim.set_weather(SimulatedWeather.SUNNY)
        sim.set_house_load(1000)
        sim._update_pv_production()
        return sim

    def test_self_use_mode_battery_charges(self, simulator):
        """Test battery charges from PV surplus in self-use mode."""
        simulator.set_battery_soc(50)
        simulator.state.pv_power = 5000  # 5kW PV
        simulator.state.house_load = 1000  # 1kW load
        
        simulator._simulate_self_use_mode(
            pv=simulator.state.pv_power,
            load=simulator.state.house_load,
            dt=1.0
        )
        
        # Battery should be charging (positive power)
        assert simulator.state.battery_power > 0
        # Grid should not be importing much
        assert simulator.state.grid_power <= 0  # Might be exporting

    def test_self_use_mode_battery_discharges(self, simulator):
        """Test battery discharges to cover load when no PV."""
        simulator.set_battery_soc(80)
        simulator.state.pv_power = 0  # No PV
        simulator.state.house_load = 2000  # 2kW load
        
        simulator._simulate_self_use_mode(
            pv=simulator.state.pv_power,
            load=simulator.state.house_load,
            dt=1.0
        )
        
        # Battery should be discharging (negative power)
        assert simulator.state.battery_power < 0

    def test_grid_control_mode_charges_battery(self, simulator):
        """Test grid control mode charges battery from grid."""
        simulator.set_battery_soc(30)
        simulator.set_remote_control_mode(RemoteControlMode.GRID_CONTROL)
        simulator.set_active_power(3000)  # 3kW from grid
        simulator.trigger_remote_control()
        
        simulator.state.pv_power = 0
        simulator.state.house_load = 500
        
        simulator._simulate_remote_control_mode(
            pv=simulator.state.pv_power,
            load=simulator.state.house_load,
            dt=1.0
        )
        
        # Battery should be charging
        assert simulator.state.battery_power > 0

    def test_battery_control_mode_discharges(self, simulator):
        """Test battery control mode discharges to grid."""
        simulator.set_battery_soc(80)
        simulator.set_remote_control_mode(RemoteControlMode.BATTERY_CONTROL)
        simulator.set_active_power(-3000)  # Discharge 3kW
        simulator.trigger_remote_control()
        
        simulator.state.pv_power = 0
        simulator.state.house_load = 500
        
        simulator._simulate_remote_control_mode(
            pv=simulator.state.pv_power,
            load=simulator.state.house_load,
            dt=1.0
        )
        
        # Battery should be discharging
        assert simulator.state.battery_power < 0

    def test_no_discharge_mode(self, simulator):
        """Test no-discharge mode prevents battery discharge."""
        simulator.set_battery_soc(80)
        simulator.set_remote_control_mode(RemoteControlMode.NO_DISCHARGE)
        simulator.trigger_remote_control()
        
        simulator.state.pv_power = 0
        simulator.state.house_load = 2000
        
        simulator._simulate_remote_control_mode(
            pv=simulator.state.pv_power,
            load=simulator.state.house_load,
            dt=1.0
        )
        
        # Battery should NOT be discharging (power >= 0)
        assert simulator.state.battery_power >= 0
        # Grid should cover the load
        assert simulator.state.grid_power > 0


class TestSimulatorBatteryConstraints:
    """Test battery constraint enforcement."""

    @pytest.fixture
    def simulator(self, simulator_config_entry_mock):
        """Create a simulator instance."""
        return SolaxSimulatorCore(simulator_config_entry_mock.data)

    def test_battery_soc_upper_limit(self, simulator):
        """Test battery stops charging when full."""
        simulator.set_battery_soc(99)
        # With 1% headroom (100 Wh) and dt=3600s, max charge power = 100 W
        constrained = simulator._apply_battery_constraints(5000, 3600.0)
        assert constrained < 5000
        assert constrained <= 100

    def test_battery_soc_lower_limit(self, simulator):
        """Test battery stops discharging when empty."""
        simulator.set_battery_soc(6)  # Just above 5% reserve (100 Wh removable)
        # With 1% removable and dt=3600s, max discharge power = 100 W
        constrained = simulator._apply_battery_constraints(-5000, 3600.0)
        assert constrained > -5000
        assert constrained >= -100

    def test_battery_power_limit_charge(self, simulator):
        """Test battery respects max charge power."""
        simulator.set_battery_soc(50)
        
        constrained = simulator._apply_battery_constraints(10000, 1.0)
        
        assert constrained <= simulator.state.max_charge_power

    def test_battery_power_limit_discharge(self, simulator):
        """Test battery respects max discharge power."""
        simulator.set_battery_soc(50)
        
        constrained = simulator._apply_battery_constraints(-10000, 1.0)
        
        assert constrained >= -simulator.state.max_discharge_power
