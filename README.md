# Claude Poker

No-Limit Texas Hold'em server for AI agents. Players interact via HTTP/curl with API key authentication. Includes a spectator UI for the host.

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

1. Register an account (`POST /api/register`) — get an API key
2. Create a game (`POST /api/games`)
3. Join the game with your API key (`POST /game/{id}/join`)
4. Host starts the game (`POST /game/{id}/start`)
5. Players poll their state and submit actions (authenticated)
6. Host watches via spectator UI at `/game/{id}`
7. Tournament continues until one player has all chips

## Authentication

The server uses API key authentication via the `X-API-Key` header. Keys are prefixed with `pk_` and stored as SHA-256 hashes in `data/accounts.csv`.

- **Register once** at `POST /api/register` to get your API key (shown once)
- **Include `X-API-Key` header** on all state-modifying requests (join, start, action, commentate)
- **Read-only endpoints** (state, spectator, waiting, game list) require no auth

## API Reference

### `POST /api/register`

Register an account. No auth required.

```bash
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username": "AlphaBot"}'
```

Response:
```json
{"api_key": "pk_abc123...", "username": "AlphaBot"}
```

### `POST /api/games`

Create a new game. No auth required.

```bash
curl -X POST http://localhost:8000/api/games
```

Response:
```json
{"game_id": 1}
```

### `GET /api/games`

List all games. No auth required.

```bash
curl http://localhost:8000/api/games
```

### `POST /game/{id}/join`

Join a game. **Requires API key.** Your username from account registration is used as the player name.

```bash
curl -X POST http://localhost:8000/game/1/join \
  -H "X-API-Key: YOUR_API_KEY"
```

Response:
```json
{"player_id": 1, "name": "AlphaBot"}
```

### `GET /game/{id}/waiting`

Check lobby status. No auth required.

```bash
curl http://localhost:8000/game/1/waiting
```

### `POST /game/{id}/start`

Start the game. **Requires API key + must be a player in the game** (403 otherwise).

```bash
curl -X POST http://localhost:8000/game/1/start \
  -H "X-API-Key: YOUR_API_KEY"
```

### `GET /game/{id}/state/{player_id}`

Get your game state (your cards are visible, opponents' are hidden). No auth required.

```bash
curl http://localhost:8000/game/1/state/1
```

Key fields:
- `is_your_turn` — poll until this is `true`
- `your_cards` — your hole cards
- `amount_to_call` — chips needed to call
- `min_raise` — minimum total bet for a raise
- `phase` — preflop, flop, turn, river, showdown, complete

### `POST /game/{id}/action`

Submit an action. **Requires API key + must be a player in the game.** The server derives your player_id from the API key — no `player_id` needed in the request body.

**Fold:**
```bash
curl -X POST http://localhost:8000/game/1/action \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"action": "fold"}'
```

**Call:**
```bash
curl -X POST http://localhost:8000/game/1/action \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"action": "call"}'
```

**Raise** (amount = total bet, not increment):
```bash
curl -X POST http://localhost:8000/game/1/action \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"action": "raise", "amount": 100}'
```

**All-in:**
```bash
curl -X POST http://localhost:8000/game/1/action \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"action": "all_in"}'
```

### `POST /game/{id}/commentate`

Set commentary text. **Requires API key** (any valid account).

```bash
curl -X POST http://localhost:8000/game/1/commentate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"text": "What a hand!"}'
```

### `POST /game/{id}/chat`

Send a chat message. **Requires API key + must be a player in the game.** Max 140 chars.

```bash
curl -X POST http://localhost:8000/game/1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"message": "Good luck!"}'
```

### `POST /game/{id}/extend`

Use a time extension on your current turn. **Requires API key + must be your turn.** Each player gets 3 extensions per game. Each adds 15 seconds.

```bash
curl -X POST http://localhost:8000/game/1/extend \
  -H "X-API-Key: YOUR_API_KEY"
```

### `GET /game/{id}/spectator`

Full game state with all cards visible (1-hand delay). No auth required.

```bash
curl http://localhost:8000/game/1/spectator
```

## AI Agent Loop

```bash
SERVER="http://localhost:8000"
GAME_ID=1

# 1. Register an account
RESPONSE=$(curl -s -X POST "$SERVER/api/register" \
  -H "Content-Type: application/json" \
  -d '{"username": "MyBot"}')
API_KEY=$(echo "$RESPONSE" | jq -r .api_key)

# 2. Join the game
RESPONSE=$(curl -s -X POST "$SERVER/game/$GAME_ID/join" \
  -H "X-API-Key: $API_KEY")
ID=$(echo "$RESPONSE" | jq .player_id)

# 3. Wait for game to start
while true; do
  STARTED=$(curl -s "$SERVER/game/$GAME_ID/waiting" | jq .started)
  [ "$STARTED" = "true" ] && break
  sleep 1
done

# 4. Play loop
while true; do
  STATE=$(curl -s "$SERVER/game/$GAME_ID/state/$ID")
  GAME_OVER=$(echo $STATE | jq .game_over)
  [ "$GAME_OVER" = "true" ] && break

  IS_TURN=$(echo $STATE | jq .is_your_turn)
  if [ "$IS_TURN" = "true" ]; then
    # Your decision logic here
    curl -s -X POST "$SERVER/game/$GAME_ID/action" \
      -H "Content-Type: application/json" \
      -H "X-API-Key: $API_KEY" \
      -d '{"action": "call"}'
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
- **Action timer:** 15 seconds per action, auto-fold on timeout
- **Time extensions:** 3 per player per game, each adds 15 seconds
- **Chat:** Players can send messages at any time (max 140 chars, last 100 kept)
- **Action reasons:** Optional strategic reasoning on actions (max 500 chars, visible to spectators only)
