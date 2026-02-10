#!/usr/bin/env bash
# monte-admin.sh — Admin CLI for Monteclaude Game API.
#
# Usage:
#   ./scripts/monte-admin.sh status                    # Show game type status
#   ./scripts/monte-admin.sh pause   <game_type>       # Disable new game creation
#   ./scripts/monte-admin.sh unpause <game_type>       # Re-enable game creation
#
# Environment:
#   GAME_API_URL  Base URL for the Game API (default: http://localhost:8001)
#   ADMIN_KEY     Admin API key (required)

set -euo pipefail

GAME_API="${GAME_API_URL:-http://localhost:8001}"

if [ -z "${ADMIN_KEY:-}" ]; then
  echo "Error: ADMIN_KEY environment variable is required."
  echo "Set it to one of the keys in ADMIN_API_KEYS on the server."
  exit 1
fi

usage() {
  echo "Usage: $(basename "$0") <command> [game_type]"
  echo ""
  echo "Commands:"
  echo "  status              Show enabled/disabled status for all game types"
  echo "  pause <game_type>   Disable new game creation (existing games unaffected)"
  echo "  unpause <game_type> Re-enable new game creation"
  echo ""
  echo "Examples:"
  echo "  $(basename "$0") status"
  echo "  $(basename "$0") pause poker"
  echo "  $(basename "$0") unpause poker"
  echo ""
  echo "Environment:"
  echo "  GAME_API_URL  Base URL (default: http://localhost:8001)"
  echo "  ADMIN_KEY     Admin API key (required)"
  exit 1
}

[ $# -lt 1 ] && usage

COMMAND="$1"
GAME_TYPE="${2:-}"

case "$COMMAND" in
  status)
    curl -sf -H "X-Admin-Key: $ADMIN_KEY" "$GAME_API/admin/status" | jq .
    ;;
  pause)
    [ -z "$GAME_TYPE" ] && { echo "Error: game_type required"; usage; }
    RESP=$(curl -sw "\n%{http_code}" -X POST -H "X-Admin-Key: $ADMIN_KEY" "$GAME_API/admin/games/$GAME_TYPE/disable")
    HTTP_CODE=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | head -n -1)
    if [ "$HTTP_CODE" = "200" ]; then
      echo "Paused '$GAME_TYPE' — new game creation disabled."
      echo "$BODY" | jq .
    else
      echo "Error ($HTTP_CODE): $(echo "$BODY" | jq -r .detail 2>/dev/null || echo "$BODY")"
      exit 1
    fi
    ;;
  unpause)
    [ -z "$GAME_TYPE" ] && { echo "Error: game_type required"; usage; }
    RESP=$(curl -sw "\n%{http_code}" -X POST -H "X-Admin-Key: $ADMIN_KEY" "$GAME_API/admin/games/$GAME_TYPE/enable")
    HTTP_CODE=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | head -n -1)
    if [ "$HTTP_CODE" = "200" ]; then
      echo "Unpaused '$GAME_TYPE' — new game creation enabled."
      echo "$BODY" | jq .
    else
      echo "Error ($HTTP_CODE): $(echo "$BODY" | jq -r .detail 2>/dev/null || echo "$BODY")"
      exit 1
    fi
    ;;
  *)
    echo "Unknown command: $COMMAND"
    usage
    ;;
esac
