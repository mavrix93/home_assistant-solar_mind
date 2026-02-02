#!/usr/bin/env python3
"""
Seed Home Assistant .storage directory for development sandbox.

This script creates the necessary .storage files to:
- Skip onboarding
- Create a default user (dev/dev)
- Pre-install Solax PV Simulator, Czech Energy Spot Prices, Open-Meteo weather, Solar Mind, and Model Context Protocol Server
- Set up a default Lovelace dashboard

Open-Meteo is used for weather forecast (good accuracy for Czech Republic and cloud coverage).
No API key required; it uses the Home zone (Prague coordinates from core.config).

Run before first `docker-compose up`:
    python dev/seed_storage.py
    # or
    ./dev/seed.sh

Default credentials: username=dev, password=dev
"""

import base64
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import bcrypt
except ImportError:
    print("Error: bcrypt is required for the seed script (HA uses bcrypt for passwords).")
    print("Install with: pip install bcrypt")
    sys.exit(1)

# Configuration
USERNAME = "dev"
PASSWORD = "dev"
DISPLAY_NAME = "Developer"

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
STORAGE_DIR = SCRIPT_DIR / "config" / ".storage"
CUSTOM_COMPONENTS = PROJECT_ROOT / "custom_components"
CZ_ENERGY_SPOT_PRICES_REPO = "https://github.com/rnovacek/homeassistant_cz_energy_spot_prices.git"
CZ_ENERGY_SPOT_PRICES_SENSOR = "sensor.current_spot_electricity_price"

# Open-Meteo: built-in HA integration, good accuracy for CZ and cloud coverage (no API key).
OPEN_METEO_ZONE = "zone.home"  # Uses HA home zone from core.config (Prague coords)
OPEN_METEO_WEATHER_ENTITY = "weather.open_meteo"  # Entity ID created by Open-Meteo integration

# Solax Simulator entity IDs (base names; coordinator resolves _2 etc. if HA assigns them).
SOLAX_BATTERY_SOC = "sensor.solax_simulator_battery_soc"
SOLAX_BATTERY_POWER = "sensor.solax_simulator_battery_power"
SOLAX_REMOTECONTROL_POWER_CONTROL = "select.solax_simulator_remote_control_power_control"
SOLAX_REMOTECONTROL_ACTIVE_POWER = "number.solax_simulator_remote_control_active_power"
SOLAX_PV_POWER = "sensor.solax_simulator_pv_power"
SOLAX_GRID_POWER = "sensor.solax_simulator_grid_power"
SOLAX_HOUSE_LOAD = "sensor.solax_simulator_house_load"
SOLAX_ENERGY_STORAGE_MODE = "select.solax_simulator_energy_storage_mode"
SOLAX_REMOTECONTROL_TRIGGER = "button.solax_simulator_remote_control_trigger"
SOLAX_REMOTECONTROL_AUTOREPEAT_DURATION = "number.solax_simulator_remote_control_autorepeat_duration"


def generate_password_hash(password: str) -> str:
    """Generate HA-compatible password hash (bcrypt, rounds=12, base64 for storage)."""
    hashed = bcrypt.hashpw(
        password.encode("utf-8")[:72],
        bcrypt.gensalt(rounds=12),
    )
    return base64.b64encode(hashed).decode("utf-8")


def generate_uuid() -> str:
    """Generate a random UUID."""
    return str(uuid.uuid4())


def generate_token() -> str:
    """Generate a random token."""
    return secrets.token_hex(32)


def generate_long_lived_token() -> str:
    """Generate a token for long-lived access (HA uses 64 bytes = 128 hex chars)."""
    return secrets.token_hex(64)


def write_json(path: Path, data: dict) -> None:
    """Write JSON file with proper formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Created: {path.relative_to(SCRIPT_DIR)}")


def create_onboarding() -> None:
    """Create onboarding file to skip initial setup.

    HA onboarding STEPS are: user, core_config, analytics, integration.
    All must be in data.done for onboarding to be considered complete.
    """
    data = {
        "version": 4,
        "minor_version": 1,
        "key": "onboarding",
        "data": {
            "done": [
                "user",
                "core_config",
                "analytics",
                "integration",
            ]
        },
    }
    write_json(STORAGE_DIR / "onboarding", data)


def create_auth(
    user_id: str,
    credential_id: str,
    refresh_token_id: str,
) -> tuple[dict, str]:
    """Create auth file with user, credentials, and a fixed MCP access token.

    We use a single refresh token (type normal) whose token string is the MCP token,
    so HA accepts it for Bearer auth without depending on long_lived_access_token handling.
    Returns (auth_data, mcp_token_string). The token is valid as Bearer for /api/*.
    """
    mcp_token = generate_long_lived_token()
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "version": 1,
        "minor_version": 1,
        "key": "auth",
        "data": {
            "users": [
                {
                    "id": user_id,
                    "group_ids": ["system-admin"],
                    "is_owner": True,
                    "is_active": True,
                    "name": DISPLAY_NAME,
                    "system_generated": False,
                    "local_only": False,
                }
            ],
            "groups": [
                {"id": "system-admin"},
                {"id": "system-users"},
                {"id": "system-read-only"},
            ],
            "credentials": [
                {
                    "id": credential_id,
                    "user_id": user_id,
                    "auth_provider_type": "homeassistant",
                    "auth_provider_id": None,
                    "data": {"username": USERNAME},
                }
            ],
            "refresh_tokens": [
                {
                    "id": refresh_token_id,
                    "user_id": user_id,
                    "client_id": None,
                    "client_name": "MCP (Cursor / dev sandbox)",
                    "client_icon": None,
                    "token_type": "normal",
                    "created_at": now,
                    "access_token_expiration": 1800.0,
                    "token": mcp_token,
                    "jwt_key": generate_token(),
                    "last_used_at": None,
                    "last_used_ip": None,
                    "credential_id": credential_id,
                    "version": None,
                },
            ],
        },
    }
    write_json(STORAGE_DIR / "auth", data)
    return data, mcp_token


def _write_mcp_token_file(token: str) -> None:
    """Write the MCP long-lived token to dev/config/.ha_mcp_token (gitignored)."""
    token_file = STORAGE_DIR.parent / ".ha_mcp_token"
    token_file.write_text(token.strip(), encoding="utf-8")
    token_file.chmod(0o600)
    print(f"  Created: {token_file.relative_to(SCRIPT_DIR)} (use as API_ACCESS_TOKEN for Cursor MCP)")


def create_auth_provider() -> None:
    """Create auth_provider.homeassistant with bcrypt-hashed password (HA uses bcrypt)."""
    password_hash = generate_password_hash(PASSWORD)
    data = {
        "version": 1,
        "minor_version": 1,
        "key": "auth_provider.homeassistant",
        "data": {
            "users": [
                {
                    "username": USERNAME,
                    "password": password_hash,
                }
            ],
        },
    }
    write_json(STORAGE_DIR / "auth_provider.homeassistant", data)


def create_core_config() -> None:
    """Create core.config with basic settings."""
    data = {
        "version": 1,
        "minor_version": 3,
        "key": "core.config",
        "data": {
            "latitude": 50.0755,
            "longitude": 14.4378,
            "elevation": 200,
            "unit_system_v2": "metric",
            "location_name": "Dev Home",
            "time_zone": "Europe/Prague",
            "external_url": None,
            "internal_url": None,
            "currency": "CZK",
            "country": "CZ",
            "language": "en",
        },
    }
    write_json(STORAGE_DIR / "core.config", data)


def create_core_uuid(instance_uuid: str) -> None:
    """Create core.uuid with instance identifier."""
    data = {
        "version": 1,
        "minor_version": 1,
        "key": "core.uuid",
        "data": {"uuid": instance_uuid},
    }
    write_json(STORAGE_DIR / "core.uuid", data)


def create_person(user_id: str, person_id: str) -> None:
    """Create person storage."""
    data = {
        "version": 2,
        "minor_version": 1,
        "key": "person",
        "data": {
            "items": [
                {
                    "id": person_id,
                    "user_id": user_id,
                    "name": DISPLAY_NAME,
                    "picture": None,
                    "device_trackers": [],
                }
            ],
            "storage_version": 2,
        },
    }
    write_json(STORAGE_DIR / "person", data)


def create_core_analytics(instance_uuid: str) -> None:
    """Create core.analytics with disabled analytics (HA expects uuid in data)."""
    data = {
        "version": 1,
        "minor_version": 1,
        "key": "core.analytics",
        "data": {
            "uuid": instance_uuid,
            "onboarded": True,
            "preferences": {},
        },
    }
    write_json(STORAGE_DIR / "core.analytics", data)


def ensure_cz_energy_spot_prices() -> None:
    """Ensure Czech Energy Spot Prices integration is in custom_components.

    Clones the HACS repo into custom_components/cz_energy_spot_prices if missing,
    so the dev sandbox has spot price data without installing HACS.
    """
    target = CUSTOM_COMPONENTS / "cz_energy_spot_prices"
    if target.exists():
        print(f"  Czech Energy Spot Prices already present: {target.relative_to(PROJECT_ROOT)}")
        return
    print("  Installing Czech Energy Spot Prices (clone from GitHub)...")
    CUSTOM_COMPONENTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cz_energy_spot_") as tmp:
        tmp_path = Path(tmp)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", CZ_ENERGY_SPOT_PRICES_REPO, str(tmp_path)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            print(f"  Warning: git clone failed: {result.stderr or result.stdout}")
            print("  Add Czech Energy Spot Prices via HACS, or clone manually into custom_components/cz_energy_spot_prices")
            return
        src = tmp_path / "custom_components" / "cz_energy_spot_prices"
        if not src.exists():
            print("  Warning: custom_components/cz_energy_spot_prices not found in repo")
            return
        shutil.copytree(src, target)
        print(f"  Created: {target.relative_to(PROJECT_ROOT)}")


def create_config_entries(
    simulator_entry_id: str,
    cz_entry_id: str,
    open_meteo_entry_id: str,
    solar_mind_entry_id: str,
    mcp_entry_id: str,
) -> None:
    """Create core.config_entries with Solax Simulator, Czech OTE, Open-Meteo, Solar Mind, and MCP Server.

    HA expects each entry to have created_at, modified_at (ISO strings),
    discovery_keys (dict), and subentries (list). Storage minor_version 5.

    If HA logs KeyError: 'created_at', remove dev/config/.storage and re-run
    this seed (the on-disk file was from an older format).
    """
    now = datetime.now(timezone.utc).isoformat()
    entries = [
        {
            "entry_id": simulator_entry_id,
            "version": 1,
            "minor_version": 1,
            "domain": "solax_pv_simulator",
            "title": "Solax Simulator",
            "data": {
                "name": "Solax Simulator",
                "battery_capacity": 14400,
                "max_pv_power": 10000,
                "max_charge_power": 5000,
                "max_discharge_power": 5000,
                "initial_soc": 50,
            },
            "options": {},
            "pref_disable_new_entities": False,
            "pref_disable_polling": False,
            "source": "user",
            "unique_id": "solax_simulator_solax_simulator",
            "disabled_by": None,
            "created_at": now,
            "modified_at": now,
            "discovery_keys": {},
            "subentries": [],
        },
        {
            "entry_id": cz_entry_id,
            "version": 1,
            "minor_version": 1,
            "domain": "cz_energy_spot_prices",
            "title": "Electricity Spot 60min Rate in CZK/kWh",
            "data": {
                "currency": "CZK",
                "unit_of_measurement": "kWh",
                "commodity": "electricity",
                "interval": "60min",
            },
            "options": {},
            "pref_disable_new_entities": False,
            "pref_disable_polling": False,
            "source": "user",
            "unique_id": "cz_energy_spot_prices_dev",
            "disabled_by": None,
            "created_at": now,
            "modified_at": now,
            "discovery_keys": {},
            "subentries": [],
        },
        {
            "entry_id": open_meteo_entry_id,
            "version": 1,
            "minor_version": 1,
            "domain": "open_meteo",
            "title": "Open-Meteo",
            "data": {"zone": OPEN_METEO_ZONE},
            "options": {},
            "pref_disable_new_entities": False,
            "pref_disable_polling": False,
            "source": "user",
            "unique_id": OPEN_METEO_ZONE,
            "disabled_by": None,
            "created_at": now,
            "modified_at": now,
            "discovery_keys": {},
            "subentries": [],
        },
        {
            "entry_id": solar_mind_entry_id,
            "version": 1,
            "minor_version": 1,
            "domain": "solar_mind",
            "title": "Solar Mind",
            "data": {
                "name": "Solar Mind",
                "solax_device_type": "modbus_remote",
                "remotecontrol_power_control": SOLAX_REMOTECONTROL_POWER_CONTROL,
                "remotecontrol_active_power": SOLAX_REMOTECONTROL_ACTIVE_POWER,
                "remotecontrol_trigger": SOLAX_REMOTECONTROL_TRIGGER,
                "battery_soc": SOLAX_BATTERY_SOC,
                "price_sensor": CZ_ENERGY_SPOT_PRICES_SENSOR,
                "price_source": "czech_ote",
                "weather_entity": OPEN_METEO_WEATHER_ENTITY,
            },
            "options": {
                "charge_price_threshold": 0.05,
                "discharge_price_threshold": 0.15,
                "min_soc": 10,
                "max_soc": 95,
                "max_charge_power": 3000,
                "max_discharge_power": 3000,
                "charge_window_start": 22,
                "charge_window_end": 6,
                "discharge_allowed": False,
                "update_interval": 5,
                "autorepeat_duration": 3600,
                "fallback_strategy": "spot_price_weather",
            },
            "pref_disable_new_entities": False,
            "pref_disable_polling": False,
            "source": "user",
            "unique_id": "solar_mind_solar_mind",
            "disabled_by": None,
            "created_at": now,
            "modified_at": now,
            "discovery_keys": {},
            "subentries": [],
        },
        {
            "entry_id": mcp_entry_id,
            "version": 1,
            "minor_version": 1,
            "domain": "mcp_server",
            "title": "Home Assistant",
            "data": {"llm_hass_api": ["assist"]},
            "options": {},
            "pref_disable_new_entities": False,
            "pref_disable_polling": False,
            "source": "user",
            "unique_id": "mcp_server_sandbox",
            "disabled_by": None,
            "created_at": now,
            "modified_at": now,
            "discovery_keys": {},
            "subentries": [],
        },
    ]
    for entry in entries:
        if "created_at" not in entry or "modified_at" not in entry:
            raise ValueError(
                "Each config entry must have created_at and modified_at (ISO strings). "
                "If HA still shows KeyError: 'created_at', remove dev/config/.storage and re-run seed."
            )
    data = {
        "version": 1,
        "minor_version": 5,
        "key": "core.config_entries",
        "data": {"entries": entries},
    }
    write_json(STORAGE_DIR / "core.config_entries", data)


def create_lovelace() -> None:
    """Create default Lovelace dashboard with Solax Simulator cards."""
    data = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace",
        "data": {
            "config": {
                "title": "Solar Mind Dev",
                "views": [
                    {
                        "title": "Overview",
                        "path": "overview",
                        "icon": "mdi:solar-power",
                        "cards": [
                            {
                                "type": "markdown",
                                "content": (
                                    "## Solar Mind Development Sandbox\n\n"
                                    "Pre-configured: **Solax PV Simulator**, **Czech Energy Spot Prices**, **Open-Meteo weather**, and **Solar Mind**. "
                                    "If you see \"Configuration error\" or unavailable entities, see README → Local Sandbox."
                                ),
                            },
                            {
                                "type": "weather",
                                "entity": OPEN_METEO_WEATHER_ENTITY,
                            },
                            {
                                "type": "entities",
                                "title": "Solax Simulator - Battery",
                                "entities": [
                                    SOLAX_BATTERY_SOC,
                                    SOLAX_BATTERY_POWER,
                                    SOLAX_REMOTECONTROL_POWER_CONTROL,
                                    SOLAX_REMOTECONTROL_ACTIVE_POWER,
                                ],
                            },
                            {
                                "type": "entities",
                                "title": "Solax Simulator - Power",
                                "entities": [
                                    SOLAX_PV_POWER,
                                    SOLAX_GRID_POWER,
                                    SOLAX_HOUSE_LOAD,
                                ],
                            },
                            {
                                "type": "entities",
                                "title": "Solax Simulator - Controls",
                                "entities": [
                                    SOLAX_ENERGY_STORAGE_MODE,
                                    SOLAX_REMOTECONTROL_TRIGGER,
                                    SOLAX_REMOTECONTROL_AUTOREPEAT_DURATION,
                                ],
                            },
                        ],
                    },
                    {
                        "title": "Solar Mind",
                        "path": "solar-mind",
                        "icon": "mdi:brain",
                        "cards": [
                            {
                                "type": "markdown",
                                "content": (
                                    "## Solar Mind Dashboard\n\n"
                                    "Solar Mind is pre-configured with Czech OTE prices, Open-Meteo weather, and the Solax Simulator."
                                ),
                            },
                            {
                                "type": "entities",
                                "title": "Solar Mind Status",
                                "entities": [
                                    "sensor.solar_mind_status",
                                    "sensor.solar_mind_recommended_action",
                                    "sensor.solar_mind_active_strategy",
                                    "sensor.solar_mind_battery_soc",
                                ],
                                "show_header_toggle": False,
                            },
                            {
                                "type": "entities",
                                "title": "Price Information",
                                "entities": [
                                    "sensor.solar_mind_current_price",
                                    "sensor.solar_mind_next_cheap_hour",
                                    "sensor.solar_mind_cheapest_hours_today",
                                ],
                                "show_header_toggle": False,
                            },
                        ],
                    },
                    {
                        "title": "Energy Plan",
                        "path": "energy-plan",
                        "icon": "mdi:calendar-clock",
                        "cards": [
                            {
                                "type": "markdown",
                                "content": (
                                    "## Energy Forecast & Plan\n\n"
                                    "24-48 hour energy planning based on weather forecast and spot prices. "
                                    "Shows when to charge/discharge batteries, expected PV generation, and cost estimates."
                                ),
                            },
                            {
                                "type": "entities",
                                "title": "Current Hour Plan",
                                "entities": [
                                    "sensor.solar_mind_current_hour_plan",
                                    "sensor.solar_mind_status",
                                    "sensor.solar_mind_battery_soc",
                                    "sensor.solar_mind_predicted_soc_6h",
                                ],
                                "show_header_toggle": False,
                            },
                            {
                                "type": "horizontal-stack",
                                "cards": [
                                    {
                                        "type": "entity",
                                        "entity": "sensor.solar_mind_pv_forecast_today",
                                        "name": "PV Today",
                                        "icon": "mdi:solar-power-variant",
                                    },
                                    {
                                        "type": "entity",
                                        "entity": "sensor.solar_mind_pv_forecast_tomorrow",
                                        "name": "PV Tomorrow",
                                        "icon": "mdi:solar-power-variant-outline",
                                    },
                                    {
                                        "type": "entity",
                                        "entity": "sensor.solar_mind_load_forecast_today",
                                        "name": "Load Today",
                                        "icon": "mdi:home-lightning-bolt",
                                    },
                                ],
                            },
                            {
                                "type": "entities",
                                "title": "Planned Actions",
                                "entities": [
                                    "sensor.solar_mind_next_planned_charge",
                                    "sensor.solar_mind_next_planned_discharge",
                                    "sensor.solar_mind_next_cheap_hour",
                                ],
                                "show_header_toggle": False,
                            },
                            {
                                "type": "horizontal-stack",
                                "cards": [
                                    {
                                        "type": "entity",
                                        "entity": "sensor.solar_mind_estimated_daily_cost",
                                        "name": "Est. Cost",
                                        "icon": "mdi:cash-minus",
                                    },
                                    {
                                        "type": "entity",
                                        "entity": "sensor.solar_mind_estimated_daily_revenue",
                                        "name": "Est. Revenue",
                                        "icon": "mdi:cash-plus",
                                    },
                                    {
                                        "type": "entity",
                                        "entity": "sensor.solar_mind_plan_horizon",
                                        "name": "Plan Horizon",
                                        "icon": "mdi:calendar-clock",
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "title": "Forecast History",
                        "path": "forecast-history",
                        "icon": "mdi:chart-line",
                        "cards": [
                            {
                                "type": "markdown",
                                "content": (
                                    "## Forecast Accuracy\n\n"
                                    "Compare predictions vs actual values to track forecast accuracy over time."
                                ),
                            },
                            {
                                "type": "entities",
                                "title": "Forecast Accuracy",
                                "entities": [
                                    "sensor.solar_mind_forecast_accuracy",
                                    "sensor.solar_mind_historical_comparison",
                                ],
                                "show_header_toggle": False,
                            },
                            {
                                "type": "entities",
                                "title": "Plan Details",
                                "entities": [
                                    "sensor.solar_mind_plan_horizon",
                                    "sensor.solar_mind_last_update",
                                ],
                                "show_header_toggle": False,
                            },
                            {
                                "type": "markdown",
                                "content": (
                                    "### How to View Historical Data\n\n"
                                    "1. Click on any sensor above to see its history graph\n"
                                    "2. Use the History panel (sidebar) for detailed comparisons\n"
                                    "3. Sensor attributes contain detailed hourly forecast vs actual data\n\n"
                                    "**Tip:** Enable the Recorder component with history to store more data."
                                ),
                            },
                        ],
                    },
                ],
            }
        },
    }
    write_json(STORAGE_DIR / "lovelace", data)


def create_lovelace_dashboards() -> None:
    """Create lovelace_dashboards registry."""
    data = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace_dashboards",
        "data": {"items": []},
    }
    write_json(STORAGE_DIR / "lovelace_dashboards", data)


def main() -> None:
    """Seed the .storage directory."""
    print(f"\nSeeding Home Assistant storage in: {STORAGE_DIR}")
    print(f"Default credentials: {USERNAME} / {PASSWORD}\n")

    # Ensure Czech Energy Spot Prices is in custom_components (clone if missing)
    ensure_cz_energy_spot_prices()

    # Generate IDs
    user_id = generate_uuid()
    credential_id = generate_uuid()
    refresh_token_id = generate_uuid()
    person_id = generate_uuid()
    instance_uuid = generate_uuid()
    simulator_entry_id = generate_uuid()
    cz_entry_id = generate_uuid()
    open_meteo_entry_id = generate_uuid()
    solar_mind_entry_id = generate_uuid()
    mcp_entry_id = generate_uuid()

    # Create storage files
    create_onboarding()
    _, mcp_token = create_auth(user_id, credential_id, refresh_token_id)
    _write_mcp_token_file(mcp_token)
    create_auth_provider()
    create_core_config()
    create_core_uuid(instance_uuid)
    create_person(user_id, person_id)
    create_core_analytics(instance_uuid)
    create_config_entries(
        simulator_entry_id,
        cz_entry_id,
        open_meteo_entry_id,
        solar_mind_entry_id,
        mcp_entry_id,
    )
    create_lovelace()
    create_lovelace_dashboards()

    print(f"\nStorage seeded successfully!")
    print(f"User ID: {user_id}")
    print(f"Simulator entry ID: {simulator_entry_id}")
    print(f"Czech OTE entry ID: {cz_entry_id}")
    print(f"Open-Meteo entry ID: {open_meteo_entry_id}")
    print(f"Solar Mind entry ID: {solar_mind_entry_id}")
    print(f"\nNext steps:")
    print(f"  1. Start Home Assistant: docker-compose -f dev/docker-compose.yml up -d")
    print(f"  2. Open: http://localhost:8123")
    print(f"  3. Login with: {USERNAME} / {PASSWORD}")
    print(
        "  4. Integrations Solax Simulator, Czech Energy Spot Prices, Open-Meteo, Solar Mind, and Model Context Protocol Server are pre-configured."
    )
    print(f"  5. MCP token for Cursor: dev/config/.ha_mcp_token (use in Cursor MCP env as API_ACCESS_TOKEN)")


if __name__ == "__main__":
    main()
