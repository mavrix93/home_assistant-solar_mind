"""Core simulator logic with no Home Assistant dependencies.

Used by simulator.py (HA integration) and by tests.
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from .const import (
    CONF_BATTERY_CAPACITY,
    CONF_INITIAL_SOC,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_PV_POWER,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_INITIAL_SOC,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_PV_POWER,
    EnergyStorageMode,
    RemoteControlMode,
    SimulatedWeather,
    WEATHER_PV_MULTIPLIER,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SimulatorState:
    """State of the Solax simulator."""

    # Battery
    battery_soc: float = 50.0  # %
    battery_power: float = 0.0  # W (positive = charging, negative = discharging)
    battery_capacity: float = DEFAULT_BATTERY_CAPACITY  # Wh
    battery_energy: float = 5000.0  # Wh (current energy stored)
    battery_temperature: float = 25.0  # °C

    # PV
    pv_power: float = 0.0  # W
    pv_voltage: float = 300.0  # V
    pv_current: float = 0.0  # A
    max_pv_power: float = DEFAULT_MAX_PV_POWER  # W

    # Grid
    grid_power: float = 0.0  # W (positive = import, negative = export)
    grid_voltage: float = 230.0  # V
    grid_frequency: float = 50.0  # Hz

    # House
    house_load: float = 500.0  # W (base load)

    # Inverter
    inverter_temperature: float = 35.0  # °C

    # Energy counters
    energy_today: float = 0.0  # kWh
    energy_total: float = 0.0  # kWh

    # Control state
    remote_control_mode: RemoteControlMode = RemoteControlMode.SELF_USE
    energy_storage_mode: EnergyStorageMode = EnergyStorageMode.SELF_USE
    active_power_setpoint: float = 0.0  # W
    autorepeat_duration: int = 3600  # seconds
    passive_grid_power: float = 0.0  # W

    # Control state timing
    remote_control_active: bool = False
    remote_control_expires: datetime | None = None

    # Simulation state
    weather: SimulatedWeather = SimulatedWeather.SUNNY
    simulated_hour: float = 12.0  # Hour of day for PV simulation
    use_real_time: bool = True

    # Limits
    max_charge_power: float = DEFAULT_MAX_CHARGE_POWER
    max_discharge_power: float = DEFAULT_MAX_DISCHARGE_POWER

    # Listeners
    listeners: list[Callable[[], None]] = field(default_factory=list)


class SolaxSimulatorCore:
    """Core simulator logic with no Home Assistant dependencies."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize from a config dict (e.g. entry.data)."""
        self._state = SimulatorState()
        self._last_update: datetime | None = None

        self._state.battery_capacity = config.get(
            CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY
        )
        self._state.max_charge_power = config.get(
            CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER
        )
        self._state.max_discharge_power = config.get(
            CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER
        )
        self._state.max_pv_power = config.get(
            CONF_MAX_PV_POWER, DEFAULT_MAX_PV_POWER
        )
        initial_soc = config.get(CONF_INITIAL_SOC, DEFAULT_INITIAL_SOC)
        self._state.battery_soc = initial_soc
        self._state.battery_energy = (initial_soc / 100.0) * self._state.battery_capacity

    @property
    def state(self) -> SimulatorState:
        """Get current simulator state."""
        return self._state

    def add_listener(self, callback_fn: Callable[[], None]) -> Callable[[], None]:
        """Add a state change listener."""
        self._state.listeners.append(callback_fn)

        def remove_listener() -> None:
            self._state.listeners.remove(callback_fn)

        return remove_listener

    def _notify_listeners(self) -> None:
        """Notify all listeners of state change."""
        for listener in self._state.listeners:
            try:
                listener()
            except Exception as e:
                _LOGGER.error("Error notifying listener: %s", e)

    def step(self, now: datetime) -> None:
        """Run one simulation step. Call this from HA timer or tests."""
        if self._last_update is None:
            self._last_update = now
            return

        dt = (now - self._last_update).total_seconds()
        self._last_update = now

        # Check remote control expiration
        if (
            self._state.remote_control_active
            and self._state.remote_control_expires
            and now >= self._state.remote_control_expires
        ):
            _LOGGER.debug("Remote control expired, returning to self-use")
            self._state.remote_control_active = False
            self._state.remote_control_mode = RemoteControlMode.SELF_USE

        # Update simulated time (or use real time)
        if self._state.use_real_time:
            self._state.simulated_hour = now.hour + now.minute / 60.0

        self._update_pv_production()
        self._update_house_load(now)
        self._simulate_power_flow(dt)
        self._update_temperatures()
        self._update_energy_counters(dt)
        self._notify_listeners()

    def _update_pv_production(self) -> None:
        """Update PV production based on time of day and weather."""
        hour = self._state.simulated_hour

        if 6 <= hour <= 18:
            angle = (hour - 6) * 15
            solar_factor = math.sin(math.radians(angle))
        else:
            solar_factor = 0.0

        weather_factor = WEATHER_PV_MULTIPLIER.get(self._state.weather, 0.5)
        variation = 1.0 + (random.random() - 0.5) * 0.1

        self._state.pv_power = (
            self._state.max_pv_power * solar_factor * weather_factor * variation
        )

        if self._state.pv_power > 0:
            self._state.pv_voltage = (
                300 + (self._state.pv_power / self._state.max_pv_power) * 100
            )
            self._state.pv_current = self._state.pv_power / self._state.pv_voltage
        else:
            self._state.pv_voltage = 0
            self._state.pv_current = 0

    def _update_house_load(self, now: datetime) -> None:
        """Update house load with daily patterns."""
        hour = self._state.simulated_hour
        base_load = 300.0
        if 7 <= hour < 9:
            base_load += 700
        elif 17 <= hour < 22:
            base_load += 1000
        elif 0 <= hour < 6:
            base_load += 100
        else:
            base_load += 400
        variation = random.gauss(1.0, 0.1)
        self._state.house_load = max(100, base_load * variation)

    def _simulate_power_flow(self, dt: float) -> None:
        """Simulate power flow between PV, battery, grid, and house."""
        pv = self._state.pv_power
        load = self._state.house_load
        if self._state.remote_control_active:
            self._simulate_remote_control_mode(pv, load, dt)
        else:
            self._simulate_self_use_mode(pv, load, dt)

    def _simulate_remote_control_mode(
        self, pv: float, load: float, dt: float
    ) -> None:
        """Simulate power flow in remote control mode."""
        mode = self._state.remote_control_mode
        setpoint = self._state.active_power_setpoint

        if mode == RemoteControlMode.GRID_CONTROL:
            target_grid_power = setpoint
            pv_to_house = min(pv, load)
            pv_surplus = pv - pv_to_house
            remaining_load = load - pv_to_house
            grid_power = remaining_load + target_grid_power
            battery_power = target_grid_power + pv_surplus

        elif mode == RemoteControlMode.BATTERY_CONTROL:
            target_battery = max(
                -self._state.max_discharge_power,
                min(self._state.max_charge_power, setpoint),
            )
            pv_to_house = min(pv, load)
            pv_surplus = pv - pv_to_house
            remaining_load = load - pv_to_house
            battery_power = target_battery
            grid_power = (
                remaining_load
                - (-battery_power if battery_power < 0 else 0)
                - pv_surplus
            )

        elif mode == RemoteControlMode.NO_DISCHARGE:
            pv_to_house = min(pv, load)
            pv_surplus = pv - pv_to_house
            remaining_load = load - pv_to_house
            battery_power = min(pv_surplus, self._state.max_charge_power)
            grid_power = remaining_load + (pv_surplus - battery_power)

        elif mode == RemoteControlMode.FEEDIN_PRIORITY:
            pv_to_house = min(pv, load)
            pv_surplus = pv - pv_to_house
            remaining_load = load - pv_to_house
            grid_power = remaining_load - pv_surplus
            battery_power = 0

        else:
            self._simulate_self_use_mode(pv, load, dt)
            return

        battery_power = self._apply_battery_constraints(battery_power, dt)
        self._state.battery_power = battery_power
        self._state.grid_power = grid_power
        self._update_battery_state(battery_power, dt)

    def _simulate_self_use_mode(self, pv: float, load: float, dt: float) -> None:
        """Simulate power flow in self-use mode."""
        pv_to_house = min(pv, load)
        pv_surplus = pv - pv_to_house
        remaining_load = load - pv_to_house
        battery_charge = min(pv_surplus, self._state.max_charge_power)
        pv_to_grid = pv_surplus - battery_charge
        battery_discharge = min(remaining_load, self._state.max_discharge_power)
        remaining_load -= battery_discharge
        battery_power = battery_charge - battery_discharge
        battery_power = self._apply_battery_constraints(battery_power, dt)
        grid_power = remaining_load - pv_to_grid
        self._state.battery_power = battery_power
        self._state.grid_power = grid_power
        self._update_battery_state(battery_power, dt)

    def _apply_battery_constraints(self, battery_power: float, dt: float) -> float:
        """Apply battery limits and SOC constraints."""
        battery_power = max(
            -self._state.max_discharge_power,
            min(self._state.max_charge_power, battery_power),
        )
        if battery_power > 0:
            max_energy_add = (
                (100 - self._state.battery_soc) / 100 * self._state.battery_capacity
            )
            max_power = (
                max_energy_add / (dt / 3600)
                if dt > 0
                else self._state.max_charge_power
            )
            battery_power = min(battery_power, max_power)
        else:
            max_energy_remove = (
                (self._state.battery_soc - 5) / 100 * self._state.battery_capacity
            )
            max_power = (
                max_energy_remove / (dt / 3600)
                if dt > 0
                else self._state.max_discharge_power
            )
            battery_power = max(battery_power, -max_power)
        return battery_power

    def _update_battery_state(self, battery_power: float, dt: float) -> None:
        """Update battery energy and SOC."""
        energy_change = battery_power * (dt / 3600)
        if battery_power > 0:
            energy_change *= 0.975
        else:
            energy_change /= 0.975
        self._state.battery_energy = max(
            0,
            min(
                self._state.battery_capacity,
                self._state.battery_energy + energy_change,
            ),
        )
        self._state.battery_soc = (
            self._state.battery_energy / self._state.battery_capacity * 100
        )

    def _update_temperatures(self) -> None:
        """Update simulated temperatures."""
        load_factor = abs(self._state.grid_power) / 5000
        self._state.inverter_temperature = 35 + load_factor * 20
        battery_load = abs(self._state.battery_power) / self._state.max_charge_power
        self._state.battery_temperature = 25 + battery_load * 10

    def _update_energy_counters(self, dt: float) -> None:
        """Update energy counters."""
        energy_kwh = self._state.pv_power * (dt / 3600) / 1000
        self._state.energy_today += energy_kwh
        self._state.energy_total += energy_kwh

    def set_remote_control_mode(self, mode: RemoteControlMode | str) -> None:
        """Set the remote control mode."""
        if isinstance(mode, str):
            mode = RemoteControlMode(mode)
        self._state.remote_control_mode = mode

    def set_energy_storage_mode(self, mode: EnergyStorageMode | str) -> None:
        """Set the energy storage mode."""
        if isinstance(mode, str):
            mode = EnergyStorageMode(mode)
        self._state.energy_storage_mode = mode

    def set_active_power(self, power: float) -> None:
        """Set the active power setpoint."""
        self._state.active_power_setpoint = power

    def set_autorepeat_duration(self, duration: int) -> None:
        """Set the autorepeat duration."""
        self._state.autorepeat_duration = duration

    def set_passive_grid_power(self, power: float) -> None:
        """Set the passive mode desired grid power."""
        self._state.passive_grid_power = power

    def trigger_remote_control(self) -> None:
        """Trigger/apply the remote control settings."""
        self._state.remote_control_active = True
        self._state.remote_control_expires = (
            datetime.now() + timedelta(seconds=self._state.autorepeat_duration)
        )

    def trigger_passive_update(self) -> None:
        """Trigger the passive mode update."""
        self._state.remote_control_active = True
        self._state.remote_control_mode = RemoteControlMode.GRID_CONTROL
        self._state.active_power_setpoint = self._state.passive_grid_power
        self._state.remote_control_expires = datetime.now() + timedelta(minutes=2)

    def set_weather(self, weather: SimulatedWeather | str) -> None:
        """Set the simulated weather condition."""
        if isinstance(weather, str):
            weather = SimulatedWeather(weather)
        self._state.weather = weather

    def set_simulated_hour(self, hour: float) -> None:
        """Set the simulated hour of day."""
        self._state.simulated_hour = hour % 24
        self._state.use_real_time = False

    def use_real_time(self, enabled: bool = True) -> None:
        """Enable or disable real-time mode."""
        self._state.use_real_time = enabled

    def set_battery_soc(self, soc: float) -> None:
        """Set the battery SOC directly (for testing)."""
        self._state.battery_soc = max(0, min(100, soc))
        self._state.battery_energy = (soc / 100) * self._state.battery_capacity

    def set_house_load(self, load: float) -> None:
        """Set a fixed house load (for testing)."""
        self._state.house_load = max(0, load)

    def reset_energy_counters(self) -> None:
        """Reset energy counters."""
        self._state.energy_today = 0
