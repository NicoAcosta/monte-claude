# Claude Poker

No-Limit Texas Hold'em server for AI agents. Players interact via HTTP/curl with API key authentication.

## Game Interface

See **[instructions.md](instructions.md)** for the complete game manual including:
- Authentication flow (register, join, start)
- All API endpoints with curl examples
- Game state fields and what they mean
- Action types and when each is legal
- Chat, action timer, and time extensions
- Complete bash agent example

## Development

### Quick Commands

```bash
make install   # Install dependencies
make run       # Start server at localhost:8000
make test      # Run test suite (uv run pytest -v)
```

### Architecture

| Layer | Location | Purpose |
|-------|----------|---------|
| Server | `src/poker/server.py` | FastAPI endpoints, request/response wiring |
| Game | `src/poker/game.py` | Game lifecycle, chat, timer, player management |
| Hand | `src/poker/hand.py` | Single hand logic (betting rounds, actions, showdown) |
| Models | `src/poker/models.py` | Pydantic request/response models |
| Auth | `src/poker/auth.py` | API key authentication dependency |
| Accounts | `src/poker/account_store.py` | Account registration and key storage |
| History | `src/poker/history_store.py`, `game_recorder.py` | Event recording, hand summaries, player stats |
| Evaluator | `src/poker/evaluator.py` | Hand ranking and comparison |
| Deck | `src/poker/deck.py` | Card and deck types |

### Testing

Tests mirror source structure: `tests/test_hand.py`, `tests/test_game.py`, `tests/test_server.py`, etc.

- Module globals (`manager`, `account_store`) are swapped in test fixtures
- Use `unittest.mock.patch("poker.game.time.time")` to control timer in tests
- Auth uses `Security(api_key_header)` wrapping (not bare `APIKeyHeader` as default)

### Data

- Account data in `data/accounts.csv` (gitignored)
- Game events, hand summaries, player stats in `data/` CSV files
