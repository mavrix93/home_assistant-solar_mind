# Documentation for Home Assistant Developers

This document is aimed at **senior Python developers** who are new to the Home Assistant integration ecosystem. It explains how custom components work in Home Assistant, how this project is structured, the entities and concepts used, and how solar PV/battery systems and Solax inverters fit in—so you can extend or maintain the codebase with confidence.

---

## Table of Contents

1. [Home Assistant Custom Integrations (Concepts)](#1-home-assistant-custom-integrations-concepts)
2. [Key Home Assistant APIs Used in This Project](#2-key-home-assistant-apis-used-in-this-project)
3. [Project Structure and Components](#3-project-structure-and-components)
4. [Entities in This Project](#4-entities-in-this-project)
5. [Solar Plant and Inverter Concepts](#5-solar-plant-and-inverter-concepts)
6. [Solax Entities: What They Are and What They Do](#6-solax-entities-what-they-are-and-what-they-do)
7. [How Solar Charging Works in This Project](#7-how-solar-charging-works-in-this-project)
8. [Pricing Modes](#8-pricing-modes)
9. [Generation Forecasting](#9-generation-forecasting)
10. [Charge-to-Target-SOC Feature](#10-charge-to-target-soc-feature)
11. [Calendar Integration](#11-calendar-integration)
12. [Services Reference](#12-services-reference)
13. [Further Reading](#13-further-reading)

---

## 1. Home Assistant Custom Integrations (Concepts)

### What is a custom integration?

A **custom integration** (or "custom component") is a Python package that lives under `config/custom_components/<domain>/` and is loaded by Home Assistant at startup. It can:

- Add new **integrations** (configured via UI or YAML)
- Expose **entities** (sensors, switches, numbers, selects, buttons, calendars, etc.)
- Register **services** that automations and scripts can call
- Use **config entries** (stored configuration per "instance" of the integration)

The **domain** is a short, unique identifier (e.g. `solar_mind`, `solax_pv_simulator`). All entities from that integration are typically prefixed by the domain (e.g. `sensor.solar_mind_current_price`).

### Manifest: identity and requirements

Every custom integration **must** have a `manifest.json` in its folder. It declares:

| Key | Purpose |
|-----|---------|
| `domain` | Unique ID; must match the folder name |
| `name` | Human-readable name in the UI |
| `version` | Semantic version (required for custom components) |
| `documentation` | Link to docs |
| `issue_tracker` | Link to issue tracker |
| `config_flow` | If `true`, setup is done via UI (no YAML required) |
| `iot_class` | e.g. `local_polling`, `cloud_polling`—hints how the integration talks to devices/APIs |
| `integration_type` | e.g. `hub`, `device`, `service` |
| `requirements` | Pip dependencies |
| `dependencies` | Other HA integrations that must load first |
| `after_dependencies` | Integrations that should be loaded before this one (e.g. `input_select`) |

Example from this project (`solar_mind/manifest.json`):

```json
{
  "domain": "solar_mind",
  "name": "Solar Mind",
  "config_flow": true,
  "iot_class": "local_polling",
  "integration_type": "hub",
  "after_dependencies": ["input_select", "open_meteo", "cz_energy_spot_prices", "solax_pv_simulator"]
}
```

**Official reference:** [Creating an integration manifest](https://developers.home-assistant.io/docs/creating_integration_manifest)

### Entry point: `__init__.py`

Home Assistant looks for:

- `async_setup(hass, config)` — called when the integration is loaded (e.g. from `configuration.yaml` or when first used). Used to set up the domain and optionally register handlers.
- `async_setup_entry(hass, entry)` — called for **each config entry** (one "instance" of the integration). Here you create your coordinator/simulator, store it in `hass.data[DOMAIN][entry.entry_id]`, and forward setup to **platforms** (sensor, number, button, calendar, etc.).

Unload is done in `async_unload_entry`: tear down platforms and remove the entry from `hass.data`.

**Official reference:** [Integration file structure](https://developers.home-assistant.io/docs/creating_integration_file_structure)

### Config flow (UI setup)

If `config_flow: true`, users add the integration via **Settings → Devices & Services → Add Integration**. The flow is implemented in `config_flow.py` by a class that subclasses `config_entries.ConfigFlow` and implements steps like `async_step_user`, `async_step_xxx`. Each step can show a form (`async_show_form`) or create the config entry (`async_create_entry`). Data is stored in the **config entry** (`entry.data`, `entry.options`); options can be changed later via the integration's "Configure" dialog.

**Official reference:** [Config entries and config flow](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)

### Platforms and entities

A **platform** is a module that adds one type of entity: `sensor`, `number`, `select`, `button`, `calendar`, etc. In `__init__.py`, after creating the "hub" (coordinator or simulator), we call:

```python
await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
```

where `PLATFORMS` is e.g. `[Platform.SENSOR, Platform.BUTTON, Platform.CALENDAR, Platform.NUMBER]`. For each platform, Home Assistant loads `sensor.py` (or `number.py`, etc.) and calls:

```python
async def async_setup_entry(hass, entry, async_add_entities):
    ...
    async_add_entities(entities)
```

So the integration creates entity instances and passes them to HA; HA then registers them in the entity registry and shows them in the UI. Entities are identified by `entity_id` (e.g. `sensor.solar_mind_current_price`) and, for stability, by `unique_id` (e.g. `{entry_id}_{sensor_key}`).

**Official reference:** [Integration platforms](https://developers.home-assistant.io/docs/creating_platform_index)

### Data flow: coordinator vs direct updates

- **DataUpdateCoordinator:** One place fetches data on an interval; entities subscribe to the coordinator and get the same data. Good for shared, periodic updates (e.g. price + forecast data).
- **Direct updates:** The "hub" (e.g. simulator) holds state and notifies listeners when it changes; entities register a callback and call `async_write_ha_state()` when notified.

This project uses **SolarMindCoordinator** (DataUpdateCoordinator) for Solar Mind and **SolaxSimulator** (custom object with listeners) for the Solax PV Simulator.

**Official reference:** [Fetching data (DataUpdateCoordinator)](https://developers.home-assistant.io/docs/integration_fetching_data)

### Services

Custom integrations can register **services** under their domain (e.g. `solar_mind.charge_battery_from_grid`). Definitions go in `services.yaml` (schema and descriptions); registration and implementation are in Python (e.g. `services.py`), using `hass.services.async_register(DOMAIN, "service_name", callback, schema)`. Services can be called from Developer Tools, automations, and scripts.

---

## 2. Key Home Assistant APIs Used in This Project

| Concept | Where used | Link / note |
|--------|-------------|-------------|
| **Config entry** | `config_flow.py`, `__init__.py`, coordinator, platforms | `ConfigEntry` holds `entry_id`, `data`, `options` |
| **DataUpdateCoordinator** | `solar_mind/ha/coordinator.py` | [Fetching data](https://developers.home-assistant.io/docs/integration_fetching_data) |
| **CoordinatorEntity** | `solar_mind/sensor.py`, `button.py`, `number.py`, `calendar.py` | Entities that take data from coordinator |
| **SensorEntity, SensorEntityDescription** | `solar_mind/sensor.py`, `solax_pv_simulator/sensor.py` | [Sensor](https://developers.home-assistant.io/docs/core/entity/sensor/) |
| **NumberEntity, ButtonEntity, CalendarEntity** | Solar Mind platforms | Number / Button / Calendar platforms |
| **SelectEntity, NumberEntity, ButtonEntity** | Solax simulator | Select / Number / Button platforms |
| **DeviceInfo** | All entity modules | Ties entities to a "device" in the device registry |
| **EntitySelector, selector.NumberSelector** | `config_flow.py` | UI for choosing entities or numeric options in config flow |
| **hass.states.get(entity_id)** | Coordinator | Read current state of any entity |
| **hass.services.async_call(domain, service, data)** | Coordinator, services | Call HA services (e.g. `select.select_option`, `number.set_value`, `button.press`) |
| **async_track_state_change_event** | Coordinator (charge-to-SOC) | Listen for entity state changes |
| **async_track_time_change** | Coordinator | Schedule actions at specific times |

Other useful docs:

- [Entity naming](https://developers.home-assistant.io/docs/entity_registry_index/#entity-naming) — `has_entity_name`, device vs entity name
- [Entity properties](https://developers.home-assistant.io/docs/core/entity) — `unique_id`, `device_class`, `state_class`, `native_value`, `extra_state_attributes`

---

## 3. Project Structure and Components

```
custom_components/
├── solar_mind/           # Main integration: price monitoring, forecasting, Solax control
│   ├── __init__.py       # Entry point, setup_entry, platforms (SENSOR, BUTTON, CALENDAR, NUMBER)
│   ├── config_flow.py    # UI setup (name, PV config, Solax entities, pricing mode, etc.)
│   ├── sensor.py         # Sensors: price, forecast, cheapest hours, charge status
│   ├── button.py         # Buttons: charge, discharge, self-use, stop, charge-to-SOC
│   ├── number.py         # Numbers: target SOC, charge power, duration
│   ├── calendar.py       # Calendar: event tracking for charge/discharge actions
│   ├── services.yaml     # Service definitions
│   ├── strings.json      # UI strings for config flow and entities
│   ├── ha/               # Home Assistant integration layer
│   │   ├── const.py      # Domain, config keys, defaults, enums
│   │   ├── coordinator.py# DataUpdateCoordinator: fetch prices, forecast, execute Solax
│   │   ├── price_adapter.py # Normalize Czech OTE / Nord Pool / generic price sensors
│   │   └── services.py   # Register and handle solar_mind.* services
│   └── mind/             # Core logic (HA-independent)
│       ├── models.py     # PriceData, HourlyPrice, SolarMindData
│       ├── types.py      # Generic types: Timeseries, Energy
│       ├── fixed_tariff.py # D57d two-rate tariff schedule
│       └── generation_forecast.py # forecast.solar API client
└── solax_pv_simulator/   # Simulated Solax inverter for testing
    ├── __init__.py       # Setup entry, create simulator, platforms, services
    ├── config_flow.py    # UI: battery capacity, max power, etc.
    ├── const.py          # Domain, sensor/select/number/button keys, modes, weather
    ├── simulator.py      # Wraps SimulatorCore, HA timer, listener registration
    ├── simulator_core.py # Pure logic: PV curve, house load, power flow, battery SOC
    ├── sensor.py, select.py, number.py, button.py  # Entity platforms
    ├── services.py       # Simulator services (set weather, SOC, house load, etc.)
    └── services.yaml     # Service definitions
```

- **Solar Mind** does not talk to hardware directly. It reads **entities** (price sensor, Solax entities) and external APIs (forecast.solar), then writes **entities** (Solax select/number/button) to control the inverter.
- **Solax PV Simulator** mimics a Solax inverter: same entity types and behaviors, so you can develop and test Solar Mind without real hardware.

---

## 4. Entities in This Project

### 4.1 Solar Mind Sensors

All sensors are under the same device (integration instance). Each sensor is built from `SolarMindData` provided by the coordinator.

| Entity ID (pattern) | Description |
|--------------------|-------------|
| `sensor.solar_mind_current_price` | Current electricity price. Attributes: `hourly_prices`, `price_mode`, `tomorrow_available`, `min_today`, `max_today`, `current_rank`, `total_hours`, `current_tariff` (for fixed mode) |
| `sensor.solar_mind_next_cheap_hour` | Next hour (HH:MM) when price is among cheapest. Attributes: `cheap_hours`, `next_start`, `next_price` |
| `sensor.solar_mind_cheapest_hours_today` | Comma-separated hours (e.g. "2, 3, 4, 5, 6, 7"). Attributes: `hours` (list of {hour, price}) |
| `sensor.solar_mind_generation_forecast` | PV generation forecast (Wh for current hour). Attributes: `hourly_forecast`, `total_today_wh`, `total_today_kwh`, `total_tomorrow_wh`, `total_tomorrow_kwh`, `source` |
| `sensor.solar_mind_charge_to_soc_status` | Charge-to-value status string. Attributes: `target_soc`, `active` |
| `sensor.solar_mind_last_update` | Last coordinator update (timestamp) |
| `sensor.solar_mind_last_error` | Last error message (diagnostic; disabled by default) |

### 4.2 Solar Mind Numbers

| Entity ID (pattern) | Description |
|--------------------|-------------|
| `number.solar_mind_target_battery_soc` | Target SOC percentage for charge-to-value (10–100%) |
| `number.solar_mind_charge_to_soc_power` | Charging power in watts (100–15000 W) |
| `number.solar_mind_charge_to_soc_duration` | Trigger duration in seconds (300–86400 s) |

### 4.3 Solar Mind Buttons

| Entity ID (pattern) | Description |
|--------------------|-------------|
| `button.solar_mind_charge_battery_from_grid` | Trigger charge from grid |
| `button.solar_mind_discharge_battery_to_grid` | Trigger discharge to grid |
| `button.solar_mind_set_self_use` | Set self-use mode |
| `button.solar_mind_set_house_use_grid` | Set house-from-grid mode (no discharge) |
| `button.solar_mind_set_battery_for_house` | Alias for self-use |
| `button.solar_mind_apply_strategy` | Refresh data |
| `button.solar_mind_stop_discharge` | Stop discharge (Enabled No Discharge mode) |
| `button.solar_mind_charge_to_target_soc` | Start charge-to-target-SOC |
| `button.solar_mind_cancel_charge_to_soc` | Cancel charge-to-SOC |

### 4.4 Solar Mind Calendar

| Entity ID (pattern) | Description |
|--------------------|-------------|
| `calendar.solar_mind_calendar` | Calendar tracking charging/discharging events |

### 4.5 Solax PV Simulator Entities

The simulator exposes the same kinds of entities a real Solax Modbus integration would, so Solar Mind can target them.

**Sensors** (read-only state):

| Key / entity | Description |
|--------------|-------------|
| `battery_soc` | Battery state of charge (%) |
| `battery_power` | Battery power (W); positive = charging, negative = discharging |
| `battery_temperature` | Battery temperature (°C) |
| `pv_power` | PV production (W) |
| `pv_voltage`, `pv_current` | PV DC voltage (V) and current (A) |
| `grid_power` | Grid power (W); positive = import, negative = export |
| `grid_voltage`, `grid_frequency` | Grid voltage (V) and frequency (Hz) |
| `house_load` | House consumption (W) |
| `inverter_temperature` | Inverter temperature (°C) |
| `energy_today`, `energy_total` | Energy (kWh) today and total |

**Select:**

| Key / entity | Description |
|--------------|-------------|
| `remotecontrol_power_control` | Remote control mode: Disabled, Enabled Grid Control, Enabled Battery Control, Enabled Self Use, Enabled No Discharge, Enabled Feedin Priority |
| `energy_storage_mode` | Energy storage mode: Self Use, Feed In Priority, Backup, Manual |

**Number:**

| Key / entity | Description |
|--------------|-------------|
| `remotecontrol_active_power` | Active power setpoint (W) for grid/battery control |
| `remotecontrol_autorepeat_duration` | Duration (s) after which the command repeats or reverts |
| `passive_desired_grid_power` | (Passive/Sofar) Desired grid power (W) |

**Button:**

| Key / entity | Description |
|--------------|-------------|
| `remotecontrol_trigger` | Apply current remote control settings (mode + power + duration) |
| `passive_update_battery_charge_discharge` | (Passive) Apply desired grid power |

---

## 5. Solar Plant and Inverter Concepts

### 5.1 Parts of a typical solar + battery system

- **PV array:** Solar panels produce DC power. Yield depends on irradiance (time of day, weather).
- **Inverter:** Converts DC (PV and often battery) to AC, connects to **grid** and **house**. It can also convert AC to DC to charge the battery from the grid.
- **Battery:** Stores energy (Wh/kWh). **State of charge (SOC)** is the fill level (0–100%).
- **Grid:** Utility connection. **Import** = power from grid to house/battery; **export** = power from house/PV/battery to grid.
- **House load:** Power consumed by the home (W or kW). Must be supplied by PV, battery, or grid.

So at any moment:  
**PV production + battery discharge + grid import = house load + battery charge + grid export** (with losses).

### 5.2 Power and energy

- **Power (W, kW):** Instantaneous flow. Positive = into battery or into house; sign conventions depend on context (e.g. grid: positive = import).
- **Energy (Wh, kWh):** Energy over time (power × time). Used for totals (e.g. energy today, energy total).
- **SOC (%):** Percentage of battery capacity currently stored. Bounded by inverter/BMS (e.g. 10–95%).

### 5.3 Charge and discharge limits

Inverters/batteries have:

- **Max charge power (W):** How fast the battery can be charged (from PV or grid).
- **Max discharge power (W):** How fast the battery can supply the house or export to grid.

The integration respects these (and optional min/max SOC) when deciding charge/discharge setpoints.

### 5.4 Operating modes (high level)

- **Self-use:** Priority is to use PV for house and battery; grid fills the gap. Typically no or limited export; battery used for house at night.
- **Charge from grid:** Grid is used to charge the battery (e.g. at cheap rate or when solar is low).
- **Discharge to grid:** Battery (and/or PV) is sent to the grid (e.g. when selling price is high).
- **No discharge / house from grid:** House is supplied from grid; battery is preserved (no discharge).

---

## 6. Solax Entities: What They Are and What They Do

Real Solax integrations (e.g. Solax Modbus) expose **select**, **number**, and **button** entities to control the inverter. Solar Mind (and the simulator) use the same contract.

### 6.1 Remote control modes (Solax "Power Control" select)

This is the main lever: *how* the inverter uses PV, battery, and grid.

| Mode | Meaning |
|------|--------|
| **Disabled** | Remote control off; inverter uses its own logic (e.g. self-use). |
| **Enabled Grid Control** | Inverter tries to achieve a **grid power setpoint** (W). Positive = import, negative = export. Used to *charge from grid* (positive setpoint) or *export* (negative). |
| **Enabled Battery Control** | Inverter tries to achieve a **battery power setpoint** (W). Positive = charge, negative = discharge. Used to charge or discharge the battery to a target power. |
| **Enabled Self Use** | Classic self-consumption: PV → house and battery; battery → house when needed; grid fills the rest. No intentional export. |
| **Enabled No Discharge** | Battery is not discharged; house can use PV and grid. Used to "preserve" battery. |
| **Enabled Feedin Priority** | Priority to feed surplus to grid (PV/battery export). |
| **Enabled Power Control** | Used for charge-to-value: sets a power setpoint to charge the battery. |

Solar Mind sets **Battery Control** for grid charging (positive power) and **Grid Control** for discharging to grid (negative grid power), and **Self Use** / **No Discharge** for the corresponding behaviors.

### 6.2 Active power and duration

- **Remote Control Active Power (number):** Setpoint in W. Meaning depends on mode: for Grid Control = desired grid power; for Battery Control = desired battery power (positive = charge, negative = discharge).
- **Autorepeat duration (number):** How long (seconds) the command is applied before the inverter may revert (e.g. back to self-use) or repeat.

### 6.3 Trigger button

After changing the **select** (mode) and **number(s)** (power, duration), something must tell the inverter to **apply** the new settings. That's the **Remote Control Trigger** button. Solar Mind (and the simulator) call `button.press` on that entity after updating select and numbers.

### 6.4 Battery SOC and optional entities

- **Battery SOC (sensor):** Read-only. Used by Solar Mind to know current level and for the charge-to-SOC feature.
- **Energy storage mode (select):** Higher-level mode (Self Use, Feed In Priority, Backup, Manual). Optional in config.

### 6.5 Passive mode (Sofar)

Some inverters (e.g. Sofar in passive mode) don't use the same select/trigger; they expose a **desired grid power** number and a **button** to apply it. Solar Mind supports this via `passive_desired_grid_power` and `passive_update_trigger` in config; the logic is the same (set power, then trigger).

---

## 7. How Solar Charging Works in This Project

### 7.1 Data flow (Solar Mind)

1. **Coordinator** runs periodically (every 30 minutes) and in `_async_update_data`:
   - **Fetches prices** from the configured price sensor (Czech OTE, Nord Pool, or generic) via `price_adapter`, or generates fixed tariff prices.
   - **Fetches generation forecast** from forecast.solar API via `generation_forecast.py`.
   - **Builds SolarMindData** with prices, forecast, and charge-to-SOC status.

2. **Sensors** read from `coordinator.data` (`SolarMindData`) and expose price, forecast, cheapest hours, etc.

3. **Manual control** is done via buttons or services, which call coordinator methods like `async_charge_from_grid()`, `async_set_self_use()`, etc.

4. **Execution on Solax**: The coordinator's execute methods call Solax select/number/button services to apply the requested mode and power.

So: **read data → expose via sensors → manual control via buttons/services → write to Solax entities**.

### 7.2 Execution on Solax (Modbus remote)

When a service or button triggers an action, the coordinator:

1. Calls `select.select_option` on **Remote Control Power Control** with the chosen mode.
2. If power is set: calls `number.set_value` on **Remote Control Active Power** (and optionally **Autorepeat Duration**).
3. Calls `button.press` on **Remote Control Trigger**.

The inverter then applies that mode and setpoint until the duration expires or a new command is sent.

### 7.3 Simulator vs real inverter

- **Solax PV Simulator** implements the same entity interface and the same modes. So Solar Mind behaves the same in tests: it reads simulator entities and calls the same select/number/button services.
- **Real Solax** (e.g. Modbus): same entity IDs and service calls; only the backend is the real inverter.

---

## 8. Pricing Modes

Solar Mind supports two pricing modes:

### 8.1 Spot Prices

Reads prices from a configured sensor (Czech OTE, Nord Pool, or generic). The price adapter normalizes different sensor formats into a common `PriceData` structure with:
- `today`: List of `HourlyPrice` for today
- `tomorrow`: List of `HourlyPrice` for tomorrow (if available)
- `current_price`: Current hour's price
- `tomorrow_available`: Whether tomorrow's prices are published

### 8.2 Fixed Tariff (D57d)

Generates prices based on the Czech D57d distribution tariff timetable. This is a two-rate (high/low) schedule defined in CET/CEST timezone.

**Workday Low-Tariff Windows:**
- 00:00–06:15
- 07:15–08:15
- 09:15–18:15
- 19:15–20:15
- 21:15–23:59

**Weekend Low-Tariff Windows:**
- 00:00–07:45
- 08:45–09:45
- 10:45–18:15
- 19:15–20:15
- 21:15–23:59

The `fixed_tariff.py` module provides:
- `is_low_tariff(dt)`: Check if a datetime falls in low-tariff period
- `build_fixed_price_data(high_price, low_price)`: Generate 24-hour price data for today and tomorrow

---

## 9. Generation Forecasting

Solar Mind fetches PV generation forecasts from the **forecast.solar** API.

### 9.1 Configuration

During setup, the user configures:
- **Azimuth**: Panel orientation (-180 to 180, 0=North, 180=South)
- **Tilt**: Panel angle (0=horizontal, 90=vertical)
- **Max PV Power**: Peak power capacity in Watts

Latitude and longitude are taken from Home Assistant's core configuration.

### 9.2 API Client

The `ForecastSolarApiGenerationForecast` class in `generation_forecast.py`:
- Queries the forecast.solar API with location and PV system parameters
- Returns a `Timeseries[Energy]` with hourly Wh predictions
- Results are cached and refreshed periodically

### 9.3 Sensor

The `sensor.solar_mind_generation_forecast` exposes:
- **State**: Current hour's predicted generation (Wh)
- **Attributes**:
  - `hourly_forecast`: Full hourly breakdown
  - `total_today_wh` / `total_today_kwh`: Total expected today
  - `total_tomorrow_wh` / `total_tomorrow_kwh`: Total expected tomorrow
  - `source`: "forecast.solar"

---

## 10. Charge-to-Target-SOC Feature

This feature allows charging the battery from grid until a specific SOC percentage is reached, then automatically stopping discharge.

### 10.1 How it works

1. User sets target SOC via `number.solar_mind_target_battery_soc`
2. User optionally adjusts power and duration numbers
3. User presses `button.solar_mind_charge_to_target_soc`
4. Coordinator:
   - Checks current SOC against target
   - Starts charging using "Enabled Power Control" mode
   - Registers a state change listener on the battery SOC sensor
5. When SOC reaches target:
   - Switches to "Enabled No Discharge" mode
   - Removes the listener
   - Updates status to "Target reached"

### 10.2 State tracking

The `sensor.solar_mind_charge_to_soc_status` shows:
- "Idle" - not active
- "Charging to X%" - in progress
- "Charging to X% (now Y%)" - in progress with current SOC
- "Target reached (X%)" - completed
- "Already at X% (target Y%)" - skipped because already at target
- "Cancelled" - user cancelled
- "Error: No SOC sensor" - configuration issue

### 10.3 Cancellation

Press `button.solar_mind_cancel_charge_to_soc` to abort. This:
- Removes the SOC listener
- Switches to "Enabled No Discharge" mode
- Updates status to "Cancelled"

---

## 11. Calendar Integration

Solar Mind includes a calendar entity that tracks charging and discharging events.

### 11.1 Event Recording

When the coordinator executes a charge or discharge action, it calls `record_calendar_event()` which adds an event to the calendar with:
- **Summary**: Action type (e.g., "Charging", "Charging to 80%")
- **Start**: Current hour (rounded down)
- **End**: Start + duration (default 1 hour)

### 11.2 Calendar Entity Features

The `calendar.solar_mind_calendar` entity supports:
- `CREATE_EVENT`: Create new events
- `DELETE_EVENT`: Remove events
- `UPDATE_EVENT`: Modify existing events

Events can be viewed in the Home Assistant calendar view or queried via the calendar API.

---

## 12. Services Reference

### Manual Control Services

| Service | Description | Parameters |
|---------|-------------|------------|
| `solar_mind.charge_battery_from_grid` | Force charge from grid | `power_w` (optional), `duration_seconds` (optional) |
| `solar_mind.discharge_battery_to_grid` | Discharge to grid | `power_w` (optional), `duration_seconds` (optional) |
| `solar_mind.set_self_use` | Set self-use mode | None |
| `solar_mind.set_battery_for_house` | Alias for self-use | None |
| `solar_mind.set_house_use_grid` | House from grid (no discharge) | None |
| `solar_mind.apply_strategy` | Refresh data | None |
| `solar_mind.charge_to_value` | Charge to target SOC | `target_soc` (optional), `power_w` (optional), `duration_seconds` (optional) |

---

## 13. Further Reading

- **Home Assistant developer docs:** [developers.home-assistant.io](https://developers.home-assistant.io/)
- **Creating an integration:** [Creating your first integration](https://developers.home-assistant.io/docs/creating_component_index/)
- **Integration structure:** [Integration file structure](https://developers.home-assistant.io/docs/creating_integration_file_structure)
- **Config flow:** [Config entries config flow handler](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)
- **Fetching data / coordinator:** [Integration fetching data](https://developers.home-assistant.io/docs/integration_fetching_data)
- **Entity concepts:** [Core entity](https://developers.home-assistant.io/docs/core/entity)
- **Calendar entity:** [Calendar entity](https://developers.home-assistant.io/docs/core/entity/calendar/)
- **Solax Modbus (community):** e.g. [homeassistant-solax-modbus](https://github.com/wills106/homeassistant-solax-modbus) — real inverter entities this project is designed to work with.
- **forecast.solar API:** [forecast.solar](https://forecast.solar/) — solar generation forecasting service

This doc should give you a clear mental model of Home Assistant custom integrations, how this repo is structured, what each entity is for, how solar and Solax concepts map to modes and setpoints, and how Solar Mind manages pricing, forecasting, and battery control.
