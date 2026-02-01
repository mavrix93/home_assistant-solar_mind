#!/bin/bash
#
# Deploy both Solar Mind and Solax PV Simulator to Home Assistant
#
# Usage: ./scripts/deploy_all.sh [OPTIONS]
#
# Options:
#   -h, --host HOST     Remote host (or set in .env)
#   -p, --path PATH     Remote config path (or set in .env)
#   -r, --restart       Restart Home Assistant after deploy
#   --dry-run           Show what would be done without doing it
#   --help              Show this help message
#

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Complete Solar Mind System Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Deploy Solar Mind
echo -e "${GREEN}Step 1: Deploying Solar Mind...${NC}"
echo ""
"$SCRIPT_DIR/deploy.sh" "$@"

echo ""
echo -e "${GREEN}Step 2: Deploying Solax PV Simulator...${NC}"
echo ""
"$SCRIPT_DIR/deploy_simulator.sh" "$@"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}All components deployed successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Restart Home Assistant (or reload integrations)"
echo "2. Add 'Solax PV Simulator' integration first"
echo "3. Add 'Solar Mind' integration and select simulator entities"
echo "4. Test the integration using simulator controls"
