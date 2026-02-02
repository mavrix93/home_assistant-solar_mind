#!/usr/bin/env bash
# Test Home Assistant dev server and MCP token.
# Usage: ./dev/test_mcp_token.sh
# Requires: curl, dev/config/.ha_mcp_token (from ./dev/seed.sh)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/config"
TOKEN_FILE="$CONFIG_DIR/.ha_mcp_token"
HA_URL="${HA_URL:-http://localhost:8123}"

echo "=== Testing Home Assistant dev server at $HA_URL ==="
echo ""

# 1. Server reachable
if ! curl -sf -o /dev/null "$HA_URL/"; then
  echo "FAIL: Cannot reach $HA_URL (is the container running?)"
  echo "  Start with: docker-compose -f dev/docker-compose.yml up -d"
  exit 1
fi
echo "OK: Server is reachable"

# 2. Token file exists
if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "FAIL: Token file not found: $TOKEN_FILE"
  echo "  Run: ./dev/seed.sh"
  exit 1
fi
echo "OK: Token file exists"

TOKEN=$(tr -d '\n' < "$TOKEN_FILE")
if [[ ${#TOKEN} -ne 128 ]]; then
  echo "WARN: Token length is ${#TOKEN} (expected 128)"
fi

# 3. Token present in auth storage (if .storage exists)
AUTH_FILE="$CONFIG_DIR/.storage/auth"
if [[ -f "$AUTH_FILE" ]]; then
  if grep -q "$TOKEN" "$AUTH_FILE" 2>/dev/null; then
    echo "OK: Token found in auth storage"
  else
    echo "WARN: Token NOT in auth storage (re-run ./dev/seed.sh, then restart HA)"
  fi
fi

# 4. API with token
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$HA_URL/api/")
if [[ "$HTTP" == "200" ]]; then
  echo "OK: API accepts token (HTTP $HTTP)"
  echo ""
  echo "MCP token is valid. Use it in Cursor MCP (API_ACCESS_TOKEN)."
  exit 0
fi

if [[ "$HTTP" == "401" ]]; then
  echo "FAIL: API returned 401 Unauthorized with token from $TOKEN_FILE"
  echo ""
  echo "The token was created by seed, but this HA instance may have loaded"
  echo "auth before the seed (or from a different .storage)."
  echo ""
  echo "Fix: Re-seed and restart HA so the MCP token is loaded:"
  echo "  docker-compose -f dev/docker-compose.yml down"
  echo "  rm -rf dev/config/.storage"
  echo "  ./dev/seed.sh"
  echo "  docker-compose -f dev/docker-compose.yml up -d"
  echo "  # Wait ~30s for HA to start, then run this script again."
  exit 1
fi

echo "FAIL: API returned HTTP $HTTP"
exit 1
