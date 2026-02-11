# Two-API Architecture Plan

Split the monolith into **Game API** (real-time game engine) and **Data API** (read/app data).

## A. Endpoint Classification

| Endpoint | API | Rationale |
|----------|-----|-----------|
| **Account & Registration** | | |
| `POST /api/register` | Data API | Account creation, no game state dependency |
| `GET /api/instructions` | Data API | Static documentation |
| **Lobby & Discovery** | | |
| `GET /` (lobby.html) | Data API | Static file serving |
| `GET /api/games` | **Hybrid** | Lists all games (read from DB + live state from Game API) |
| `POST /api/games` | Game API | Creates game, returns game ID |
| **Game Interaction** | | |
| `GET /game/{id}` (spectator.html) | Data API | Static file serving |
| `POST /game/{id}/join` | Game API | Mutates in-memory Game object |
| `GET /game/{id}/waiting` | Game API | Live game state (pre-start) |
| `POST /game/{id}/start` | Game API | Mutates Game object |
| `GET /game/{id}/state` | Game API | Live player state |
| `POST /game/{id}/action` | Game API | Mutates Hand state |
| `POST /game/{id}/resign` | Game API | Mutates Game object |
| `GET /game/{id}/spectator` | Game API | Live spectator view |
| **Chat & Timer** | | |
| `POST /game/{id}/chat` | Game API | Mutates Game._chat_log |
| `POST /game/{id}/extend` | Game API | Mutates Game._time_extensions |
| **Escrow** | | |
| `GET /game/{id}/escrow` | Data API | Reads game config, computes escrow (no live state) |
| `GET /game/{id}/funding` | Data API | Polls blockchain, updates config.funded |
| `GET /game/{id}/settlement` | Data API | Reads final game state, signs settlement |
| `GET /game/{id}/offchain-settlement` | Data API | Reads config.offchain_settlement |
| **History** | | |
| `GET /api/games/{id}/history` | Data API | Reads from game_events table |
| `GET /api/games/{id}/hands` | Data API | Reads from hand_summaries table |
| `GET /api/stats/{username}` | Data API | Reads from player_stats table |
| **Streams** | | |
| `POST /game/{id}/streams` | Game API | Creates in-memory Stream object |
| `GET /game/{id}/streams` | Game API | Lists streams (from memory) |
| `GET /api/streams` | Game API | Lists all streams (from memory) |
| `POST /stream/{id}/commentate` | Game API | Mutates Stream.commentary_text |
| `GET /stream/{id}` (page) | Data API | Static file serving |
| `GET /stream/{id}/data` | Game API | Live spectator view with commentary |
| **Bankroll** | | |
| `POST /api/faucet` | Data API | Mutates balances table |
| `GET /api/balance` | Data API | Reads balances table |

### Key Observations

1. **Game API owns live state**: Anything touching `Game`, `Hand`, `Stream` objects stays in Game API
2. **Data API owns persistence**: All DB reads/writes for historical data, accounts, balances
3. **Hybrid case**: `/api/games` list endpoint needs both DB game records AND live state (player_count, current hand_number)

## B. Shared Dependencies

| Module | Game API | Data API | Sharing Strategy |
|--------|----------|----------|------------------|
| **Database Stores** | writes events | reads + writes | **PostgreSQL** — both connect to same DB |
| `AccountStore` | auth | registration | PostgreSQL |
| `BalanceStore` | join debit | faucet, settlement | PostgreSQL |
| `GameEventStore` | write only | read only | PostgreSQL |
| `HandSummaryStore` | write only | read only | PostgreSQL |
| `PlayerStatsStore` | write only | read only | PostgreSQL |
| **Core Models** | yes | yes | **Shared Python library** |
| `models.py` (Pydantic) | yes | yes | Shared `poker-common` package |
| `game_mode.py` | yes | yes | Shared |
| `payout.py` | no | yes | Move to Data API |
| **Authentication** | yes | yes | Both validate API keys via `AccountStore` |
| **Blockchain** | no | yes | `escrow.py`, `escrow_service.py` -> Data API |

### Sharing Strategy

**PostgreSQL as Integration Point**
- Game API writes events to `game_events`, `hand_summaries`, `player_stats` via `GameRecorder`
- Data API reads these tables for history endpoints
- Both APIs read/write `balances` (Game API: join debit, Data API: faucet + settlement)
- Both APIs read `accounts` for authentication

**Shared Library**
- Create `poker-common` package for shared models, constants, types
- Both APIs depend on this package
- Includes: `models.py`, `game_mode.py`, `history_models.py`, etc.

**No HTTP calls between APIs**
- Game API never calls Data API
- Data API never calls Game API
- All communication via PostgreSQL

## C. Communication Pattern: Lobby Hybrid

**Problem:** `/api/games` needs live data (player_count, started, game_over) from Game API.

**Solution: `game_metadata` table** updated by Game API on every state change:

```sql
CREATE TABLE game_metadata (
    game_id INTEGER PRIMARY KEY,
    player_count INTEGER NOT NULL,
    player_names TEXT[] NOT NULL,
    started BOOLEAN NOT NULL DEFAULT FALSE,
    game_over BOOLEAN NOT NULL DEFAULT FALSE,
    winner TEXT,
    hand_number INTEGER NOT NULL DEFAULT 0,
    last_updated TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Update triggers:**
- Player join -> increment player_count, append to player_names
- Game start -> set started=true
- Hand completion -> increment hand_number
- Game over -> set game_over=true, winner

Data API reads `game_metadata` for lobby list. Eventual consistency (~1s lag) is acceptable for lobby UX.

## D. Directory Structure

```
packages/
├── poker-common/                    # Shared library
│   ├── pyproject.toml
│   └── src/poker_common/
│       ├── models.py               # Pydantic models
│       ├── game_mode.py
│       ├── history_models.py
│       └── deck.py                 # Card/Deck types
│
├── game-api/                        # Game engine server (port 8001)
│   ├── pyproject.toml
│   └── src/game_api/
│       ├── server.py               # FastAPI app (game endpoints)
│       ├── auth.py
│       ├── game.py, hand.py
│       ├── game_manager.py, game_service.py, game_config.py
│       ├── stream.py, stream_manager.py
│       ├── game_recorder.py        # Writes to DB stores
│       ├── evaluator.py, deck.py
│       ├── db.py
│       ├── account_store.py        # Read-only (auth)
│       ├── balance_store.py        # Read/write (join debit, settlement)
│       ├── history_store.py        # Write-only (events, summaries, stats)
│       └── settlement_service.py
│
└── data-api/                        # Read/app-data server (port 8000)
    ├── pyproject.toml
    └── src/data_api/
        ├── server.py               # FastAPI app (data endpoints)
        ├── auth.py
        ├── db.py
        ├── account_store.py        # Read/write (registration)
        ├── balance_store.py        # Read/write (faucet, balance queries)
        ├── history_store.py        # Read-only (history, stats)
        ├── escrow.py, escrow_service.py
        ├── balance_service.py, payout.py
        └── static/                 # Frontend files
```

## E. Implementation Plan

### Phase 1: Extract Shared Library (PR #1)
- Create `packages/poker-common/` with `pyproject.toml`
- Move `models.py`, `game_mode.py`, `history_models.py`, `deck.py` (types only)
- Update server to depend on `poker-common`

### Phase 2: Add game_metadata Table (PR #2)
- Add migration: `CREATE TABLE game_metadata`
- Update `GameManager` to write to `game_metadata` on state changes
- Add `GameMetadataStore` with upsert methods

### Phase 3: Split Game API (PR #3)
- Create `packages/game-api/` directory structure
- Copy game-related files
- Create new `server.py` with only game endpoints
- Configure to run on port 8001

### Phase 4: Split Data API (PR #4)
- Create `packages/data-api/` directory structure
- Copy data-related files
- Create new `server.py` with data endpoints
- Move static files, implement `/api/games` via `game_metadata` table
- Configure to run on port 8000

### Phase 5: Integration Testing (PR #5)
- Update frontend to call correct API endpoints
- Add integration tests spanning both APIs
- Test full game lifecycle end-to-end

### Phase 6: Deployment & Cleanup (PR #6-7)
- Add health checks, configure separate processes/containers
- Remove old monolith, update documentation

## F. Open Questions & Recommendations

| # | Question | Recommendation |
|---|----------|----------------|
| 1 | Game creation: which API owns `POST /api/games`? | Data API owns public endpoint, calls Game API internal endpoint |
| 2 | Lobby data freshness | Eventual consistency via PostgreSQL (~1s lag), no WebSockets needed |
| 3 | Stream persistence | Keep in-memory (ephemeral), no DB table needed |
| 4 | Auth shared state | Yes — both APIs share `accounts` table |
| 5 | Settlement timing | Keep in Game API's `on_game_over` callback |
| 6 | Escrow/blockchain ops | Data API handles all escrow/blockchain |
| 7 | State version | Stays entirely within Game API |
| 8 | Migration strategy | Blue-green deployment: deploy split APIs to new ports, test, cutover |

## G. Key Trade-offs

| Aspect | Benefit | Cost |
|--------|---------|------|
| **Decoupling** | Game engine scales independently, restarts don't affect data layer | Two codebases, two deployments |
| **PostgreSQL integration** | No HTTP latency between APIs, strong consistency for balances | Shared DB schema coupling |
| **Lobby consistency** | Simple implementation via `game_metadata` table | ~1s lag for lobby data |
| **Shared library** | DRY models and types | Extra package to maintain |
