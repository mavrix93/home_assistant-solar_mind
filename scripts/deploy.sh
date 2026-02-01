#!/bin/bash
#
# Deploy Solar Mind to Home Assistant
#
# Usage: ./scripts/deploy.sh [OPTIONS]
#
# Options:
#   -h, --host HOST     Remote host (or set DEPLOY_HOST/SOLAR_MIND_HOST in .env)
#   -p, --path PATH     Remote config path (or set DEPLOY_PATH/SOLAR_MIND_PATH in .env)
#   -r, --restart       Restart Home Assistant after deploy
#   --dry-run           Show what would be done without doing it
#   --help              Show this help message
#
# Copy .env.example to .env and set DEPLOY_HOST, DEPLOY_PATH for local deploy config.
#

set -e

# Script directory and project root (for .env)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$PROJECT_ROOT/.env"
  set +a
fi

# Configuration from env (.env or -h/-p); no hardcoded defaults
REMOTE_HOST="${SOLAR_MIND_HOST:-${DEPLOY_HOST:-}}"
REMOTE_PATH="${SOLAR_MIND_PATH:-${DEPLOY_PATH:-}}"
RESTART=false
DRY_RUN=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SOURCE_DIR="$PROJECT_ROOT/custom_components/solar_mind"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--host)
            REMOTE_HOST="$2"
            shift 2
            ;;
        -p|--path)
            REMOTE_PATH="$2"
            shift 2
            ;;
        -r|--restart)
            RESTART=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            head -20 "$0" | tail -15
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

if [ -z "$REMOTE_HOST" ] || [ -z "$REMOTE_PATH" ]; then
    echo -e "${RED}Error: REMOTE_HOST and REMOTE_PATH must be set.${NC}"
    echo "  Option 1: Copy .env.example to .env and set DEPLOY_HOST, DEPLOY_PATH"
    echo "  Option 2: Pass -h HOST and -p PATH on the command line"
    exit 1
fi

# Verify source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    echo -e "${RED}Error: Source directory not found: $SOURCE_DIR${NC}"
    exit 1
fi

# Build destination path
DEST_DIR="$REMOTE_PATH/custom_components/solar_mind"

echo -e "${GREEN}Solar Mind Deployment${NC}"
echo "================================"
echo "Source:      $SOURCE_DIR"
echo "Destination: $REMOTE_HOST:$DEST_DIR"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}DRY RUN - No changes will be made${NC}"
    echo ""
fi

# Test SSH connection
echo -n "Testing SSH connection... "
if [ "$DRY_RUN" = false ]; then
    if ssh -o ConnectTimeout=5 "$REMOTE_HOST" "echo ok" > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAILED${NC}"
        echo ""
        echo "Could not connect to $REMOTE_HOST"
        echo "Make sure:"
        echo "  1. The host is reachable"
        echo "  2. SSH key authentication is configured"
        echo "  3. The username is correct"
        exit 1
    fi
else
    echo -e "${YELLOW}SKIPPED (dry run)${NC}"
fi

# Create destination directory if needed
echo -n "Creating destination directory... "
if [ "$DRY_RUN" = false ]; then
    ssh "$REMOTE_HOST" "mkdir -p '$DEST_DIR'" 2>/dev/null
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}SKIPPED (dry run)${NC}"
fi

# Sync files
echo "Syncing files..."
RSYNC_OPTS="-avz --delete"
RSYNC_OPTS="$RSYNC_OPTS --exclude '__pycache__'"
RSYNC_OPTS="$RSYNC_OPTS --exclude '*.pyc'"
RSYNC_OPTS="$RSYNC_OPTS --exclude '*.pyo'"
RSYNC_OPTS="$RSYNC_OPTS --exclude '.git'"
RSYNC_OPTS="$RSYNC_OPTS --exclude '.pytest_cache'"
RSYNC_OPTS="$RSYNC_OPTS --exclude 'tests'"
RSYNC_OPTS="$RSYNC_OPTS --exclude '.mypy_cache'"

if [ "$DRY_RUN" = true ]; then
    RSYNC_OPTS="$RSYNC_OPTS --dry-run"
fi

# shellcheck disable=SC2086
rsync $RSYNC_OPTS "$SOURCE_DIR/" "$REMOTE_HOST:$DEST_DIR/"

echo ""
echo -e "${GREEN}Files synced successfully!${NC}"

# Restart Home Assistant if requested
if [ "$RESTART" = true ]; then
    echo ""
    echo -n "Restarting Home Assistant... "
    if [ "$DRY_RUN" = false ]; then
        # Try ha command first (Home Assistant OS), fall back to docker
        if ssh "$REMOTE_HOST" "command -v ha &> /dev/null"; then
            ssh "$REMOTE_HOST" "ha core restart" 2>/dev/null
        elif ssh "$REMOTE_HOST" "docker ps | grep -q homeassistant"; then
            ssh "$REMOTE_HOST" "docker restart homeassistant" 2>/dev/null
        else
            echo -e "${YELLOW}Could not find HA restart command${NC}"
            echo "Please restart Home Assistant manually via:"
            echo "  - Developer Tools → YAML → Restart"
            echo "  - Or: ha core restart"
        fi
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}SKIPPED (dry run)${NC}"
    fi
else
    echo ""
    echo -e "${YELLOW}Note: Home Assistant was not restarted.${NC}"
    echo "To apply changes, either:"
    echo "  1. Run this script with -r/--restart flag"
    echo "  2. Go to Developer Tools → YAML → Restart"
    echo "  3. Reload the integration from Settings → Devices & Services"
fi

echo ""
echo -e "${GREEN}Deployment complete!${NC}"
