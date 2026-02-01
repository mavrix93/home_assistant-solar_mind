# Solar Mind

A Home Assistant custom integration that optimizes your solar PV and battery system using spot electricity prices and weather forecasts.

## Features

- **Spot Price Optimization**: Charges battery when electricity prices are low, uses battery when prices are high
- **Weather-Aware**: Considers solar production forecast to optimize battery usage
- **Czech OTE Support**: Native support for Czech electricity spot prices (OTE) via [Czech Energy Spot Prices](https://github.com/rnovacek/homeassistant_cz_energy_spot_prices)
- **Nord Pool Support**: Also works with Nord Pool prices
- **Multiple Strategies**: Choose from spot price optimization, time-of-use, self-use only, or manual control
- **Strategy Selector**: Switch strategies via Home Assistant helper entity (can be automated)
- **Dashboard Entities**: Comprehensive sensors for building dashboards
- **Services**: Manual control via HA services for automations

## Prerequisites

1. **Solax Inverter** with one of:
   - [Solax Modbus Integration](https://github.com/wills106/homeassistant-solax-modbus) (HACS) - Recommended for Gen4 inverters
   - Sofar inverter in Passive Mode

2. **Spot Price Sensor**:
   - **Czech Republic**: [Czech Energy Spot Prices](https://github.com/rnovacek/homeassistant_cz_energy_spot_prices) integration
   - **Nordic/Baltic**: [Nord Pool](https://www.home-assistant.io/integrations/nordpool/) integration
   - **Other**: Any sensor providing hourly prices

3. **Weather Entity** (optional): Any weather integration for solar forecast

## Installation

### Manual Installation

1. Copy the `custom_components/solar_mind` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration → Search for "Solar Mind"

### Using Deploy Script

From this repository, set your deploy target via a local `.env` file (never committed), then run:

```bash
cp .env.example .env
# Edit .env and set DEPLOY_HOST (e.g. user@your-ha-host) and DEPLOY_PATH (e.g. /config)
./scripts/deploy.sh
```

Options: `-h HOST`, `-p PATH`, `-r` (restart HA), `--dry-run`. See `.env.example` for all variables.  
**Repo safety:** `.env` is listed in `.gitignore`; never commit it. The repository can be published without leaking local hostnames or paths.

## Configuration

### Initial Setup

1. **Solax Control Type**: Choose between Modbus Remote Control (Gen4) or Passive Mode (Sofar)

2. **Solax Entities**: Select your Solax integration entities:
   - Remote Control Power Control (select)
   - Remote Control Active Power (number)
   - Remote Control Trigger (button)
   - Battery SOC sensor (optional)

3. **Price Sensor**: Select your spot price sensor and source type:
   - Czech OTE (cz_energy_spot_prices)
   - Nord Pool
   - Generic

4. **Weather Entity**: Optionally select a weather entity for solar forecasting

5. **Strategy**: Configure strategy selector entity and fallback strategy

### Options

After setup, configure options:

| Option | Description | Default |
|--------|-------------|---------|
| Strategy Selector Entity | input_select to choose active strategy | - |
| Fallback Strategy | Strategy when selector unavailable | Spot price + weather |
| Charge Price Threshold | Charge from grid below this price | 0.05 CZK/kWh |
| Discharge Price Threshold | Sell to grid above this price | 0.15 CZK/kWh |
| Min SOC | Minimum battery percentage | 10% |
| Max SOC | Maximum battery percentage | 95% |
| Max Charge Power | Maximum grid charging power | 3000 W |
| Max Discharge Power | Maximum grid discharge power | 3000 W |
| Charge Window Start | Start of low-rate window | 22 (10 PM) |
| Charge Window End | End of low-rate window | 6 (6 AM) |
| Discharge Allowed | Enable selling to grid | false |
| Update Interval | Strategy update frequency | 5 min |
| Autorepeat Duration | Solax command duration | 3600 s |

## Strategies

### Spot Price + Weather (default)

The main optimization strategy that:
- Charges from grid when price is below threshold and in charge window
- Discharges to grid (if allowed) when price is above threshold
- Uses self-use mode when solar forecast is good
- Preserves battery when prices are medium

### Time of Use

Fixed schedule based on charge window:
- Charges during configured window (e.g., night hours)
- Uses self-use or no-discharge outside window
- Ignores spot prices

### Self Use Only

Simple mode where inverter manages everything:
- No grid charging
- No grid selling
- Battery charges from PV, discharges for house load

### Manual

No automatic control:
- Use services to manually control the system
- Strategy runs but doesn't execute commands

## Dashboard Entities

| Entity | Description |
|--------|-------------|
| `sensor.solar_mind_status` | Current status (charging, discharging, self_use, etc.) |
| `sensor.solar_mind_recommended_action` | Human-readable recommendation |
| `sensor.solar_mind_current_price` | Current spot price with attributes |
| `sensor.solar_mind_active_strategy` | Currently active strategy |
| `sensor.solar_mind_strategy_mode` | Detailed strategy decision |
| `sensor.solar_mind_next_cheap_hour` | Next hour below charge threshold |
| `sensor.solar_mind_cheapest_hours_today` | List of cheapest hours today |
| `sensor.solar_mind_last_update` | Last strategy run time |
| `sensor.solar_mind_next_action` | Reason for current action |
| `sensor.solar_mind_battery_soc` | Battery SOC from last read |
| `sensor.solar_mind_last_error` | Last error (diagnostic) |

## Services

### solar_mind.charge_battery_from_grid

Force charge the battery from grid.

```yaml
service: solar_mind.charge_battery_from_grid
data:
  power_w: 3000  # optional
  duration_seconds: 3600  # optional
```

### solar_mind.discharge_battery_to_grid

Discharge battery to grid (sell).

```yaml
service: solar_mind.discharge_battery_to_grid
data:
  power_w: 3000  # optional
  duration_seconds: 3600  # optional
```

### solar_mind.set_self_use

Set inverter to self-use mode.

```yaml
service: solar_mind.set_self_use
```

### solar_mind.set_battery_for_house

Use battery for house (alias for self-use).

```yaml
service: solar_mind.set_battery_for_house
```

### solar_mind.set_house_use_grid

House uses grid, battery preserved.

```yaml
service: solar_mind.set_house_use_grid
```

### solar_mind.apply_strategy

Immediately run and apply strategy.

```yaml
service: solar_mind.apply_strategy
```

## Strategy Selector Helper

To switch strategies from the dashboard or automations, create an `input_select` helper:

1. Go to Settings → Devices & Services → Helpers
2. Add Helper → Dropdown
3. Name: "Solar Mind Strategy"
4. Options (use exact values):
   - `spot_price_weather`
   - `time_of_use`
   - `self_use_only`
   - `manual`
5. In Solar Mind options, select this entity as Strategy Selector

Now you can switch strategies from the UI or via automations:

```yaml
service: input_select.select_option
target:
  entity_id: input_select.solar_mind_strategy
data:
  option: self_use_only
```

## Example Dashboard Card

```yaml
type: entities
title: Solar Mind
entities:
  - entity: sensor.solar_mind_status
  - entity: sensor.solar_mind_recommended_action
  - entity: sensor.solar_mind_current_price
  - entity: sensor.solar_mind_active_strategy
  - entity: sensor.solar_mind_battery_soc
  - entity: sensor.solar_mind_cheapest_hours_today
  - entity: sensor.solar_mind_next_cheap_hour
```

## Example Automation

Charge battery when price is very low:

```yaml
automation:
  - alias: "Force charge on very low price"
    trigger:
      - platform: numeric_state
        entity_id: sensor.solar_mind_current_price
        below: 0.01
    condition:
      - condition: numeric_state
        entity_id: sensor.solar_mind_battery_soc
        below: 80
    action:
      - service: solar_mind.charge_battery_from_grid
        data:
          power_w: 5000
          duration_seconds: 3600
```

## Troubleshooting

### Prices not loading

- Check that your price sensor is available and has the expected attributes
- For Czech OTE: verify the sensor has hourly prices in attributes
- For Nord Pool: verify `raw_today` and `raw_tomorrow` attributes exist

### Commands not executing

- Verify Solax entity IDs are correct in the config
- Check that the Solax integration is working (test manually via Developer Tools)
- Check logs for errors: `Logger: custom_components.solar_mind`

### Strategy not changing

- Verify the strategy selector entity exists and has correct options
- Check that the entity state matches a strategy key exactly
- Check the fallback strategy setting

## Solax PV Simulator (Sandbox Mode)

For testing and development, this project includes a **Solax PV Simulator** component that creates virtual Solax entities. This allows you to test Solar Mind without a real inverter.

### Simulator Features

- **Simulated Inverter Entities**: All entities expected by Solar Mind
  - `select.solax_simulator_remotecontrol_power_control` - Remote control mode
  - `number.solax_simulator_remotecontrol_active_power` - Power setpoint
  - `number.solax_simulator_remotecontrol_autorepeat_duration` - Duration
  - `button.solax_simulator_remotecontrol_trigger` - Apply settings
  - `sensor.solax_simulator_battery_soc` - Battery state of charge
  - And many more sensors (PV power, grid power, temperatures, etc.)

- **Realistic PV Simulation**: 
  - Solar curve based on time of day
  - Weather effects on production
  - Configurable max PV power

- **Battery Simulation**:
  - Charge/discharge based on mode
  - SOC limits enforced
  - Efficiency losses modeled

- **Control Services**:
  - `solax_pv_simulator.set_weather` - Set simulated weather
  - `solax_pv_simulator.set_simulated_hour` - Set time of day
  - `solax_pv_simulator.set_battery_soc` - Set battery level
  - `solax_pv_simulator.set_house_load` - Set house consumption

### Deploying the Simulator

Use the same `.env` as for Solar Mind (DEPLOY_HOST, DEPLOY_PATH), or pass `-h` / `-p`:

```bash
# Deploy simulator only (uses .env)
./scripts/deploy_simulator.sh

# Deploy both Solar Mind and Simulator
./scripts/deploy_all.sh

# Override host/path on the command line
./scripts/deploy_simulator.sh -h user@your-ha-host -p /config -r
```

### Using the Simulator

1. Deploy the simulator to Home Assistant
2. Add the "Solax PV Simulator" integration
3. Configure battery capacity, max PV power, etc.
4. Add "Solar Mind" integration
5. Select the simulator entities during Solar Mind setup

## Dependencies

This project uses three separate dependency mechanisms; keep them consistent when adding or changing deps.

| Layer | File | Purpose |
|-------|------|---------|
| **Home Assistant (runtime)** | `custom_components/solar_mind/manifest.json` | Declares what HA installs when the integration loads. Use `requirements` for pip packages (pinned, e.g. `"package==1.0.0"`), `dependencies` for HA core domains (e.g. `["http"]`), `after_dependencies` for load order. Solar Mind has no pip runtime deps (`requirements: []`). |
| **Dev/test (source of truth)** | `pyproject.toml` | PEP 621 `[project.optional-dependencies]`: `test` = unit tests only, `test-ha` = unit + config flow tests (includes Home Assistant). Python 3.11+. Install with `pip install -e ".[test]"` or `pip install -e ".[test-ha]"`. |
| **Dev/test (pip -r)** | `requirements-test.txt`, `requirements-test-ha.txt` | Plain pip requirement files for users who prefer `pip install -r`. Must be kept in sync with `pyproject.toml` optional-dependencies `test` and `test-ha`. |

**Guidelines:**

- **Runtime (HA)**: Edit only `manifest.json`. Do not add third-party libs unless the integration needs them at runtime; use pinned versions.
- **Dev/test**: Edit `pyproject.toml` first. Then update the corresponding `requirements-test*.txt` so both install paths stay equivalent.
- **Pytest**: Pytest options live in `pyproject.toml` under `[tool.pytest.ini_options]` (no separate `pytest.ini`).

## Testing

Tests use **pytest** with **pytest-asyncio** for async tests. **Python 3.11+** is required.

### Requirements

- Python 3.11 or newer (use `pyenv` or `.python-version` in the repo)
- Install: `pip install -r requirements-test.txt` or `pip install -e ".[test]"`

### Setup

```bash
# Use Python 3.11 (pyenv, or system 3.11)
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
```

### Run tests

```bash
.venv/bin/python -m pytest tests/ -v
```

Async tests (e.g. config flow) run automatically via `asyncio_mode = auto` in `pyproject.toml`.

- **Unit tests** (31 tests): strategies, models, price adapter. No HA required; `homeassistant` is mocked.
- **Config flow tests** (`test_config_flow.py`): require `pytest-homeassistant-custom-component`. Skipped if that package is not installed.

**To run the config flow tests** (including the 3 that are otherwise skipped):

```bash
# Install HA test package (~500MB+ with homeassistant and deps; ensure enough disk space)
.venv/bin/pip install -r requirements-test-ha.txt

# Run config flow tests only
.venv/bin/python -m pytest tests/test_config_flow.py -v

# Or run all Solar Mind tests (no skips)
.venv/bin/python -m pytest tests/test_strategies.py tests/test_models.py tests/test_price_adapter.py tests/test_config_flow.py -v
```

To run only Solar Mind unit tests (without HA package):

```bash
.venv/bin/python -m pytest tests/test_strategies.py tests/test_models.py tests/test_price_adapter.py tests/test_config_flow.py -v
```

With coverage:

```bash
.venv/bin/python -m pytest tests/ -v --cov=custom_components.solar_mind --cov-report=term-missing
```

### Test categories

- **test_strategies.py**: Solar Mind strategies (spot price, time-of-use, self-use, manual)
- **test_models.py**: Data models (PriceData, StrategyOutput, etc.)
- **test_price_adapter.py**: Price adapter (Czech OTE, Nord Pool)
- **test_config_flow.py**: Config flow (async; needs pytest-homeassistant-custom-component)

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.
