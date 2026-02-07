# Poker Game Orchestration Skill

Orchestrate an AI poker game: start the server, register agents with personalities, launch a commentator, and run the game to completion.

## Prerequisites

- The poker server code is in the `claude-poker/` directory
- Python venv with dependencies installed (`make install`)

## Steps

### 1. Ensure the Server Is Running

Check if the server is already running on port 8000. If not, start it:

```bash
# Check if server is up
curl -s http://localhost:8000/api/games > /dev/null 2>&1

# If not running, start it in the background
cd claude-poker && .venv/bin/uvicorn poker.server:app --host 0.0.0.0 --port 8000 &
```

Wait until the server responds before proceeding.

### 2. Ask the User for Player Configuration

Ask the user how many players (2-8) and for each player:
- **Name**: A character name (e.g., "Wild Bill", "The Professor")
- **Personality**: A one-sentence personality description that will shape their play style

If the user doesn't specify, use these defaults (3 players):
- "Wild Bill" — Aggressive cowboy who bets big and talks bigger
- "The Professor" — Calculated, analytical, rarely bluffs, speaks in probabilities
- "Lady Luck" — Superstitious risk-taker who follows gut feelings

### 3. Create a Game

```bash
curl -s -X POST http://localhost:8000/api/games
```

Save the `game_id` from the response.

### 4. Register and Join All Players

For each player, register an account and join the game:

```bash
# Register account (save the API key!)
RESPONSE=$(curl -s -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"username": "PLAYER_NAME"}')
API_KEY=$(echo "$RESPONSE" | jq -r .api_key)

# Join the game
curl -s -X POST http://localhost:8000/game/GAME_ID/join \
  -H "X-API-Key: $API_KEY"
```

Save each player's `api_key` and `player_id`.

### 5. Start the Game

Any registered player can start the game (requires their API key):

```bash
curl -s -X POST http://localhost:8000/game/GAME_ID/start \
  -H "X-API-Key: $API_KEY"
```

### 6. Launch the Commentator Subagent

Launch a background subagent with this prompt:

> You are a poker commentator. Your job is to watch the game and provide entertaining, insightful commentary.
>
> The game ID is {GAME_ID}. The server is at http://localhost:8000.
>
> Every 5-8 seconds, poll GET http://localhost:8000/game/{GAME_ID}/spectator to see the game state.
> After each poll, if something interesting happened (new actions, phase changes, big bets), POST commentary:
>
> ```bash
> curl -s -X POST http://localhost:8000/game/GAME_ID/commentate \
>   -H "Content-Type: application/json" \
>   -H "X-API-Key: YOUR_API_KEY" \
>   -d '{"text": "YOUR COMMENTARY HERE"}'
> ```
>
> Commentary style:
> - Be dramatic and entertaining, like a sports broadcaster
> - Comment on the cards, pot size, phase changes, big bets, bluffs, all-ins, and surprising plays
> - Reference players by name
> - Keep each comment under 100 characters
> - NEVER repeat or narrate what players said in their comments — they speak for themselves. Focus on the ACTION and STRATEGY, not their words.
> - Check `recent_actions` for `reason` fields — these reveal agent reasoning. You can reference their strategic thinking in your commentary.
> - When the game is over (game_over: true), give a final sendoff and stop
>
> Poll loop: GET /game/{GAME_ID}/spectator -> analyze -> POST /game/{GAME_ID}/commentate -> sleep 5-8s -> repeat
> Stop when game_over is true in the response.

### 7. Launch Each Player Subagent

For each registered player, launch a background subagent with this prompt template:

> You are {NAME}, a poker player. {PERSONALITY_DESCRIPTION}
>
> Your player_id is {ID}. Your API key is {API_KEY}. The game ID is {GAME_ID}. The server is at http://localhost:8000.
>
> Read the game instructions from: claude-poker/instructions.md
>
> Your game loop:
> 1. GET http://localhost:8000/game/{GAME_ID}/state/{ID}
> 2. If game_over is true, stop
> 3. If is_your_turn is false, wait 1 second and poll again
> 4. If is_your_turn is true:
>    a. Analyze your cards, the community cards, pot, opponents' bets/actions
>    b. Decide your action based on your personality
>    c. Include a short trash-talk comment (stay in character!) — max 140 chars
>    d. Include a `reason` explaining your strategic thinking (spectators can see this but opponents cannot) — max 500 chars
>    e. POST your action to /game/{GAME_ID}/action with comment and reason fields
> 5. Repeat from step 1
>
> IMPORTANT:
> - All actions require the X-API-Key header — no player_id in the request body
> - Only act when is_your_turn is true
> - If you get an error, read it and adjust (don't retry the same action)
> - Use check/call conservatively, raise/bet when strong, fold weak hands
> - Your personality should influence your decisions: {PERSONALITY_HINT}
> - Always include a comment that fits your character
> - You can also send chat messages at any time (not just your turn): POST /game/{GAME_ID}/chat
>
> Example action with comment and reason:
> ```bash
> curl -s -X POST http://localhost:8000/game/GAME_ID/action \
>   -H "Content-Type: application/json" \
>   -H "X-API-Key: API_KEY" \
>   -d '{"action": "call", "comment": "YOUR TRASH TALK", "reason": "Strategic reasoning here"}'
> ```

### 8. Monitor the Game

After launching all agents, periodically poll the spectator endpoint to track progress:

```bash
curl -s http://localhost:8000/game/GAME_ID/spectator | jq '{hand: .hand_number, phase: .phase, game_over: .game_over, winner: .winner}'
```

Report to the user:
- When new hands start
- When players go all-in or get eliminated
- When the game ends and who won

### 9. Report Results

When the game is over:
1. Announce the winner
2. Show the final spectator state
3. Summarize highlights (big hands, eliminations, memorable comments)
4. Stop all background agents

## Notes

- The spectator UI is available at http://localhost:8000/ for visual viewing
- The lobby page lists all games at http://localhost:8000/api/games
- All agents use curl via bash to interact with the server
- The commentator sees all cards and reasons (spectator view), players only see their own cards and cannot see opponents' reasons
- Player agents should poll every ~1 second, commentator every ~5-8 seconds
- Chat messages are max 140 chars, action reasons are max 500 chars
