"""Unit tests for GameMetadataStore."""

from core.db import get_pool
from core.game_metadata_store import GameMetadataStore


class TestGameMetadataStore:
    def test_create_and_list(self):
        store = GameMetadataStore(get_pool())
        store.create(game_id="game-1", mode="offchain", buy_in=100, max_players=2)
        rows = store.list_all()
        assert len(rows) == 1
        assert rows[0].game_id == "game-1"
        assert rows[0].mode == "offchain"
        assert rows[0].buy_in == 100

    def test_exists(self):
        store = GameMetadataStore(get_pool())
        assert store.exists("nonexistent") is False
        store.create(game_id="game-1", mode="offchain", buy_in=0, max_players=0)
        assert store.exists("game-1") is True

    def test_update_player_joined(self):
        store = GameMetadataStore(get_pool())
        store.create(game_id="game-1", mode="offchain", buy_in=0, max_players=0)
        store.update_player_joined("game-1", "Alice")
        store.update_player_joined("game-1", "Bob")
        rows = store.list_all()
        assert rows[0].player_count == 2
        assert rows[0].player_names == ["Alice", "Bob"]

    def test_update_started(self):
        store = GameMetadataStore(get_pool())
        store.create(game_id="game-1", mode="offchain", buy_in=0, max_players=0)
        store.update_started("game-1")
        rows = store.list_all()
        assert rows[0].started is True

    def test_update_hand_number(self):
        store = GameMetadataStore(get_pool())
        store.create(game_id="game-1", mode="offchain", buy_in=0, max_players=0)
        store.update_hand_number("game-1", 5)
        rows = store.list_all()
        assert rows[0].hand_number == 5

    def test_update_game_over(self):
        store = GameMetadataStore(get_pool())
        store.create(game_id="game-1", mode="offchain", buy_in=0, max_players=0)
        store.update_game_over("game-1", "Alice")
        rows = store.list_all()
        assert rows[0].game_over is True
        assert rows[0].winner == "Alice"

    def test_update_funded(self):
        store = GameMetadataStore(get_pool())
        store.create(game_id="game-1", mode="onchain", buy_in=100, max_players=2)
        store.update_funded("game-1")
        rows = store.list_all()
        assert rows[0].funded is True

    def test_create_with_optional_fields(self):
        store = GameMetadataStore(get_pool())
        store.create(
            game_id="game-1", mode="onchain", buy_in=100, max_players=2,
            token="0x1234", token_decimals=18, token_symbol="MONTE",
            action_timeout=60.0,
        )
        rows = store.list_all()
        assert rows[0].token == "0x1234"
        assert rows[0].token_symbol == "MONTE"
        assert rows[0].action_timeout == 60.0
