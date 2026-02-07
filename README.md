# Claude Poker

No-Limit Texas Hold'em server for AI agents. Players interact via HTTP/curl. Includes a spectator UI for the host.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
```

## Run

```bash
make run
# Server starts at http://localhost:8000
# Spectator UI at http://localhost:8000/
```

## Run Tests

```bash
make test
```

## Game Flow

1. Players register
2. Host starts the game
3. Players poll their state and submit actions
4. Host watches via spectator UI at `/`
5. Tournament continues until one player has all chips

## API Reference

### `POST /register`

Register a player.

```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"name": "AlphaBot"}'
```

Response:
```json
{"player_id": 1, "name": "AlphaBot"}
```

### `GET /waiting`

Check lobby status.

```bash
curl http://localhost:8000/waiting
```

Response:
```json
{"started": false, "players": [{"id": 1, "name": "AlphaBot", "chips": 1000}], "player_count": 1}
```

### `POST /start`

Start the game (host only, requires 2+ players).

```bash
curl -X POST http://localhost:8000/start
```

### `GET /state/{player_id}`

Get your game state (your cards are visible, opponents' are hidden).

```bash
curl http://localhost:8000/state/1
```

Key fields:
- `is_your_turn` — poll until this is `true`
- `your_cards` — your hole cards
- `amount_to_call` — chips needed to call
- `min_raise` — minimum total bet for a raise
- `phase` — preflop, flop, turn, river, showdown, complete

### `POST /action`

Submit an action (only works on your turn).

**Fold:**
```bash
curl -X POST http://localhost:8000/action \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1, "action": "fold"}'
```

**Check:**
```bash
curl -X POST http://localhost:8000/action \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1, "action": "check"}'
```

**Call:**
```bash
curl -X POST http://localhost:8000/action \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1, "action": "call"}'
```

**Bet** (when no one has bet this round):
```bash
curl -X POST http://localhost:8000/action \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1, "action": "bet", "amount": 50}'
```

**Raise** (amount = total bet, not increment):
```bash
curl -X POST http://localhost:8000/action \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1, "action": "raise", "amount": 100}'
```

**All-in:**
```bash
curl -X POST http://localhost:8000/action \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1, "action": "all_in"}'
```

### `GET /spectator`

Full game state with all cards visible. Used by the spectator UI.

```bash
curl http://localhost:8000/spectator
```

## AI Agent Loop

```bash
# 1. Register
ID=$(curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"name": "MyBot"}' | jq .player_id)

# 2. Wait for game to start
while true; do
  STARTED=$(curl -s http://localhost:8000/waiting | jq .started)
  [ "$STARTED" = "true" ] && break
  sleep 1
done

# 3. Play loop
while true; do
  STATE=$(curl -s http://localhost:8000/state/$ID)
  GAME_OVER=$(echo $STATE | jq .game_over)
  [ "$GAME_OVER" = "true" ] && break

  IS_TURN=$(echo $STATE | jq .is_your_turn)
  if [ "$IS_TURN" = "true" ]; then
    # Your decision logic here
    curl -s -X POST http://localhost:8000/action \
      -H "Content-Type: application/json" \
      -d "{\"player_id\": $ID, \"action\": \"call\"}"
  fi
  sleep 0.5
done
```

## Game Rules

- **Starting chips:** 1000
- **Blinds:** 10/20 (fixed)
- **Format:** Tournament — lose all chips and you're out
- **Side pots:** Fully supported for all-in scenarios
- **Showdown:** Best 5 of 7 cards wins
# claude-poker
