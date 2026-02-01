#!/bin/bash
#
# Seed Home Assistant .storage for development sandbox.
# Run this once before first `docker-compose up`.
#
# Installs: Solax PV Simulator, Czech Energy Spot Prices (clone from GitHub),
# Open-Meteo weather (built-in), and Solar Mind. Czech OTE is cloned into custom_components if missing.
#
# Usage: ./dev/seed.sh
#
# Default credentials: dev / dev
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Home Assistant Development Sandbox Setup ==="
echo ""

# Check if Python is available
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "Error: Python not found. Please install Python 3.11+."
    exit 1
fi

# Check Python version
PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Using Python $PY_VERSION"

# Run seed script
cd "$PROJECT_ROOT"
$PYTHON dev/seed_storage.py

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start Home Assistant:"
echo "  docker-compose -f dev/docker-compose.yml up -d"
echo ""
echo "To view logs:"
echo "  docker-compose -f dev/docker-compose.yml logs -f"
echo ""
echo "To stop:"
echo "  docker-compose -f dev/docker-compose.yml down"
