# Solar Mind

A Home Assistant custom integration that optimizes your solar PV and battery system using spot electricity prices, fixed tariffs, and solar generation forecasts.

If you're new to the PVE or HA, check [this document](./DOCUMENTATION.md)

## Features

- **Spot Price Optimization**: Charges battery when electricity prices are low, uses battery when prices are high
- **Fixed Tariff Support**: Two-rate pricing (high/low) with Czech D57d distribution tariff timetable
- **PV Generation Forecast**: Solar production forecasting via forecast.solar API
- **Czech OTE Support**: Native support for Czech electricity spot prices (OTE) via [Czech Energy Spot Prices](https://github.com/rnovacek/homeassistant_cz_energy_spot_prices)
- **Nord Pool Support**: Also works with Nord Pool prices
- **Charge-to-Target-SOC**: Charge battery to a specific SOC and automatically stop
- **Calendar Integration**: Track charging/discharging events on a calendar entity
- **Dashboard Cards**: Example ApexCharts dashboard configurations included
- **Services**: Manual control via HA services for automations

## Prerequisites

1. **Solax Inverter** with one of:
   - [Solax Modbus Integration](https://github.com/wills106/homeassistant-solax-modbus) (HACS) - Recommended for Gen4 inverters
   - Sofar inverter in Passive Mode

2. **Spot Price Sensor** (for spot pricing mode):
   - **Czech Republic**: [Czech Energy Spot Prices](https://github.com/rnovacek/homeassistant_cz_energy_spot_prices) integration
   - **Nordic/Baltic**: [Nord Pool](https://www.home-assistant.io/integrations/nordpool/) integration
   - **Other**: Any sensor providing hourly prices

 **Weather Entity**  for solar forecast is not needed, the integration using api.forecast.solar API directly

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

## Configuration

### Initial Setup

1. **Name**: A name for this Solar Mind instance

2. **Solax Control Type**: Choose between Modbus Remote Control (Gen4) or Passive Mode (Sofar)

3. **PV System Configuration**: Configure your solar panel parameters for generation forecasting:
   - **Azimuth**: Panel azimuth angle (-180 to 180, 0=North, 180=South)
   - **Tilt**: Panel tilt angle (0=horizontal, 90=vertical)
   - **Max PV Power**: Maximum peak power output in Watts

4. **Solax Entities**: Select your Solax integration entities:
   - Remote Control Power Control (select)
   - Remote Control Active Power (number)
   - Remote Control Trigger (button)
   - Remote Control Autorepeat Duration (optional)
   - Battery SOC sensor

5. **Pricing Mode**: Choose between:
   - **Spot Prices**: Real-time OTE sensor for dynamic pricing
   - **Fixed Tariff**: Two-rate schedule (high/low) with D57d distribution tariff timetable

6. **Price Sensor** (for spot mode): Select your spot price sensor

7. **Fixed Tariff Prices** (for fixed mode):
   - High Tariff Price (CZK/kWh)
   - Low Tariff Price (CZK/kWh)

### Options

After setup, configure options:

| Option | Description | Default |
|--------|-------------|---------|
| Charge Price Threshold | Charge from grid below this price | 0.05 CZK/kWh |
| Discharge Price Threshold | Sell to grid above this price | 0.15 CZK/kWh |
| Min SOC | Minimum battery percentage | 10% |
| Max SOC | Maximum battery percentage | 95% |
| Max Charge Power | Maximum grid charging power | 3000 W |
| Max Discharge Power | Maximum grid discharge power | 3000 W |
| Charge Window Start | Start of low-rate window | 22 (10 PM) |
| Charge Window End | End of low-rate window | 6 (6 AM) |
| Discharge Allowed | Enable selling to grid | false |
| Update Interval | Data update frequency | 30 min |
| Autorepeat Duration | Solax command duration | 3600 s |

## Entities

### Sensors

| Entity | Description |
|--------|-------------|
| `sensor.solar_mind_current_price` | Current electricity price with attributes (hourly prices, min/max today, price mode) |
| `sensor.solar_mind_next_cheap_hour` | Next hour below charge threshold |
| `sensor.solar_mind_cheapest_hours_today` | List of cheapest hours today |
| `sensor.solar_mind_generation_forecast` | PV generation forecast from forecast.solar (Wh for current hour, hourly forecast in attributes) |
| `sensor.solar_mind_charge_to_soc_status` | Charge-to-value status (Idle, Charging to X%, Target reached, etc.) |
| `sensor.solar_mind_last_update` | Last data update time |
| `sensor.solar_mind_last_error` | Last error (diagnostic, disabled by default) |

### Numbers

| Entity | Description |
|--------|-------------|
| `number.solar_mind_target_battery_soc` | Target SOC percentage for charge-to-value (10–100%) |
| `number.solar_mind_charge_to_soc_power` | Charging power for charge-to-value (100–15000 W) |
| `number.solar_mind_charge_to_soc_duration` | Trigger duration for charge-to-value (300–86400 s) |

### Buttons

| Entity | Description |
|--------|-------------|
| `button.solar_mind_charge_battery_from_grid` | Start charging battery from grid |
| `button.solar_mind_discharge_battery_to_grid` | Start discharging battery to grid |
| `button.solar_mind_set_self_use` | Set inverter to self-use mode |
| `button.solar_mind_set_house_use_grid` | Set house to use grid (preserve battery) |
| `button.solar_mind_set_battery_for_house` | Use battery for house (alias for self-use) |
| `button.solar_mind_apply_strategy` | Refresh data and run strategy |
| `button.solar_mind_stop_discharge` | Stop battery discharge (sets "Enabled No Discharge" mode) |
| `button.solar_mind_charge_to_target_soc` | Start charging to target SOC |
| `button.solar_mind_cancel_charge_to_soc` | Cancel an in-progress charge-to-value |

### Calendar

| Entity | Description |
|--------|-------------|
| `calendar.solar_mind_calendar` | Calendar tracking charging/discharging events |

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

Refresh data and apply any pending actions.

```yaml
service: solar_mind.apply_strategy
```

### solar_mind.charge_to_value

Charge the battery from the grid until a target SOC is reached, then automatically stop discharge. This uses four Solax remote control entities under the hood:

1. **Mode** is set to `Enabled Power Control` via the configured power control select
2. **Charging power** is set via the configured active power number
3. **Trigger duration** is set via the configured autorepeat duration number
4. **Action is triggered** via the configured trigger button

The integration monitors the configured Battery SOC sensor. When the target is reached, it switches to `Enabled No Discharge` mode to stop discharging (preserving the battery). You can also press `button.solar_mind_stop_discharge` at any time to manually stop discharge.

All parameters are optional — if omitted, the current values from the corresponding number entities are used (defaults: target SOC 80%, power 5000 W, duration 3600 s).

```yaml
service: solar_mind.charge_to_value
data:
  target_soc: 80          # optional, 10–100 %
  power_w: 5000           # optional, charging power in watts
  duration_seconds: 3600  # optional, trigger duration in seconds
```

You can also control this feature interactively from the UI:

1. Set `number.solar_mind_target_battery_soc` to the desired SOC %
2. Adjust `number.solar_mind_charge_to_soc_power` (default 5000 W)
3. Adjust `number.solar_mind_charge_to_soc_duration` (default 3600 s)
4. Press `button.solar_mind_charge_to_target_soc` to start
5. Monitor progress via `sensor.solar_mind_charge_to_soc_status`
6. Press `button.solar_mind_cancel_charge_to_soc` to abort

## Fixed Tariff (D57d)

When using Fixed Tariff pricing mode, Solar Mind uses the Czech D57d distribution tariff timetable:

**Workday Low-Tariff Windows (CET):**
- 00:00–06:15
- 07:15–08:15
- 09:15–18:15
- 19:15–20:15
- 21:15–23:59

**Weekend Low-Tariff Windows (CET):**
- 00:00–07:45
- 08:45–09:45
- 10:45–18:15
- 19:15–20:15
- 21:15–23:59

Hours not listed are high-tariff periods. The `sensor.solar_mind_current_price` entity will show attributes including `current_tariff` (low/high) when in fixed mode.

## Example Dashboard Card

```yaml
type: entities
title: Solar Mind
entities:
  - entity: sensor.solar_mind_current_price
  - entity: sensor.solar_mind_generation_forecast
  - entity: sensor.solar_mind_cheapest_hours_today
  - entity: sensor.solar_mind_next_cheap_hour
  - entity: sensor.solar_mind_charge_to_soc_status
  - entity: number.solar_mind_target_battery_soc
  - entity: button.solar_mind_charge_to_target_soc
```

### ApexCharts Dashboard

The `lovelace/solar_dashboard.yaml` file contains example ApexCharts card configurations for visualizing:
- Real-time power flow (PV, Load, Battery)
- Battery state of charge
- Today's energy summary
- PV generation curves
- PV vs House Load comparison
- Battery charge/discharge flow
- Self-sufficiency metrics
- Grid cost with tariff visualization

Requires the [ApexCharts Card](https://github.com/RomRider/apexcharts-card) from HACS.

## Example Automation

Charge battery when price is very low:

```yaml
automation:
  - alias: "Force charge on very low price"
    trigger:
      - platform: numeric_state
        entity_id: sensor.solar_mind_current_price
        below: 0.01
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
- For Fixed Tariff: check that high/low prices were configured during setup

### Commands not executing

- Verify Solax entity IDs are correct in the config
- Check that the Solax integration is working (test manually via Developer Tools)
- Check logs for errors: `Logger: custom_components.solar_mind`

### Generation forecast not working

- Verify latitude/longitude in Home Assistant config
- Check PV system parameters (azimuth, tilt, max power)
- The forecast.solar API may have rate limits

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

## Local Sandbox (Docker)

For local development and testing, you can run a complete Home Assistant instance with Docker. The sandbox comes pre-configured with:

- Default user (`dev` / `dev`)
- Solax PV Simulator already installed
- Model Context Protocol Server (MCP) for Cursor/LLM clients
- Default dashboard with simulator entities

### Quick Start

```bash
# 1. Seed the storage (creates user, installs simulator, sets up dashboard)
#    Requires bcrypt: pip install bcrypt
./dev/seed.sh

# 2. Start Home Assistant
docker-compose -f dev/docker-compose.yml up -d

# 3. Open in browser
open http://localhost:8123

# 4. Login with: dev / dev
```

### How It Works

The `dev/` directory contains:

- `docker-compose.yml` – Runs the official Home Assistant Container image
- `config/configuration.yaml` – Minimal HA config with debug logging enabled
- `seed_storage.py` – Creates `.storage` files (user, integrations, dashboard)
- `seed.sh` – Wrapper script to run the seed

The repo's `custom_components/` is mounted read-only into the container, so code changes take effect after restarting HA.

### Common Commands

```bash
# Start
docker-compose -f dev/docker-compose.yml up -d

# View logs
docker-compose -f dev/docker-compose.yml logs -f

# Restart (after code changes)
docker-compose -f dev/docker-compose.yml restart

# Stop
docker-compose -f dev/docker-compose.yml down

# Reset (delete all state, re-seed)
rm -rf dev/config/.storage
./dev/seed.sh
docker-compose -f dev/docker-compose.yml up -d
```

### Adding Solar Mind

1. Open http://localhost:8123 and log in
2. Go to **Settings → Devices & Services → Add Integration**
3. Search for "Solar Mind"
4. Select the Solax Simulator entities during setup:
   - Remote Control Power Control: `select.solax_simulator_remotecontrol_power_control`
   - Remote Control Active Power: `number.solax_simulator_remotecontrol_active_power`
   - Remote Control Trigger: `button.solax_simulator_remotecontrol_trigger`
   - Battery SOC: `sensor.solax_simulator_battery_soc`
5. For price sensor, create a helper (`input_number`) or use a mock sensor

### Notes

- The seed script requires **bcrypt** (`pip install bcrypt`) for HA-compatible password hashing.
- Use `docker-compose` (with hyphen). If you have Docker Compose V2 only, use `docker compose` (with space) instead.
- The default password (`dev`) is for development only – don't expose this instance to the internet
- On Apple Silicon Macs, the official HA image works natively (multi-arch)

### Cursor + Home Assistant MCP

The sandbox seeds the [Model Context Protocol Server](https://www.home-assistant.io/integrations/mcp_server/) integration so Cursor (or other MCP clients) can talk to the dev instance. Use it to validate changes by querying entities and calling services via MCP tools.

**One-time setup:**

1. **Install mcp-proxy** (Cursor uses stdio; HA exposes Streamable HTTP):
   ```bash
   uv tool install git+https://github.com/sparfenyuk/mcp-proxy
   # or: pip install mcp-proxy  (if available)
   ```

2. **Get the MCP token** (created by seed, survives restarts until you re-seed):
   - After running `./dev/seed.sh`, the token is in `dev/config/.ha_mcp_token` (gitignored).
   - Use its contents as `API_ACCESS_TOKEN` in Cursor MCP.

3. **Add the MCP server in Cursor:**
   - Open Cursor **Settings** → **MCP** → **Add new global MCP server**
   - Paste the contents of `dev/cursor-mcp.example.json`, then set `API_ACCESS_TOKEN` to the contents of `dev/config/.ha_mcp_token`
   - Restart Cursor; the "Home Assistant" server should show green when the sandbox is running.

## Dependencies

This project uses three separate dependency mechanisms; keep them consistent when adding or changing deps.

| Layer | File | Purpose |
|-------|------|---------|
| **Home Assistant (runtime)** | `custom_components/solar_mind/manifest.json` | Declares what HA installs when the integration loads. Use `requirements` for pip packages (pinned), `dependencies` for HA core domains, `after_dependencies` for load order. Solar Mind has no pip runtime deps (`requirements: []`). |
| **Dev/test (source of truth)** | `pyproject.toml` | PEP 621 `[project.optional-dependencies]`: `test` = unit tests only, `test-ha` = unit + config flow tests (includes Home Assistant). Python 3.11+. |
| **Dev/test (pip -r)** | `requirements-test.txt`, `requirements-test-ha.txt` | Plain pip requirement files for users who prefer `pip install -r`. Must be kept in sync with `pyproject.toml`. |

## Testing

Tests use **pytest** with **pytest-asyncio** for async tests. **Python 3.11+** is required.

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

With coverage:

```bash
.venv/bin/python -m pytest tests/ -v --cov=custom_components.solar_mind --cov-report=term-missing
```

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.
