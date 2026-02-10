"""Tests for core.state_builders — pure functions that build player/spectator state."""

from core.game_config import GameConfig
from core.game_mode import GameMode
from core.state_builders import (
    build_poker_player_state,
    build_poker_spectator_state,
    build_dice_player_state,
    build_dice_spectator_state,
)
from dice.game import DiceGame
from poker.game import Game, BIG_BLIND, SMALL_BLIND
from poker.models import (
    PlayerStateResponse,
    SpectatorResponse,
)
from dice.models import DiceStateResponse, DiceSpectatorResponse


def _default_config(**overrides) -> GameConfig:
    base = dict(
        mode=GameMode.OFFCHAIN,
        buy_in=1000,
        max_players=6,
        token=None,
        token_decimals=0,
        token_symbol=None,
    )
    base.update(overrides)
    return GameConfig(**base)


# ── Poker spectator ──────────────────────────────────────


class TestBuildPokerSpectatorState:
    def test_before_start(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        config = _default_config()

        resp = build_poker_spectator_state(game, config)

        assert isinstance(resp, SpectatorResponse)
        assert resp.phase == "waiting"
        assert resp.hand_number == 0
        assert resp.started is False
        assert resp.game_over is False
        assert len(resp.players) == 2
        assert resp.players[0].name == "Alice"
        assert resp.players[1].name == "Bob"
        assert resp.community_cards == []
        assert resp.pot == 0
        assert resp.timer is None
        assert resp.small_blind == SMALL_BLIND
        assert resp.big_blind == BIG_BLIND
        assert resp.mode == GameMode.OFFCHAIN

    def test_during_hand(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        config = _default_config()

        resp = build_poker_spectator_state(game, config)

        # During the first hand the spectator sees hand_number 0
        # (previous_hand is None, so the "waiting" branch fires)
        # Actually: if game.started and previous_hand is None → we get waiting branch
        # but with started=True
        assert isinstance(resp, SpectatorResponse)
        assert resp.started is True

    def test_after_hand_completion(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        config = _default_config()

        # Play a hand to completion: one player folds
        hand = game.current_hand
        assert hand is not None
        cp = hand.current_player
        assert cp is not None
        game.do_action(cp.id, "fold")

        # Now previous_hand is set
        assert game.previous_hand is not None

        resp = build_poker_spectator_state(game, config)
        assert isinstance(resp, SpectatorResponse)
        assert resp.started is True
        # After fold, the spectator sees the completed hand's phase
        assert resp.phase == "complete"
        assert resp.community_cards is not None
        assert len(resp.recent_actions) > 0

    def test_overrides_applied(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        config = _default_config()

        resp = build_poker_spectator_state(
            game, config,
            commentary_text="Hello spectators!",
            stream_id=42,
        )
        assert resp.commentary_text == "Hello spectators!"
        assert resp.stream_id == 42

    def test_config_fields_propagated(self):
        config = _default_config(
            buy_in=5000,
            token_symbol="MONTE",
            max_players=4,
            mode=GameMode.ONCHAIN,
            escrow_address="0x1234",
        )
        game = Game()
        game.register("Alice")
        game.register("Bob")

        resp = build_poker_spectator_state(game, config)
        assert resp.buy_in == 5000
        assert resp.token_symbol == "MONTE"
        assert resp.max_players == 4
        assert resp.mode == GameMode.ONCHAIN
        assert resp.escrow_address == "0x1234"


# ── Poker player state ───────────────────────────────────


class TestBuildPokerPlayerState:
    def test_during_hand(self):
        game = Game()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        game.start()
        config = _default_config()

        resp = build_poker_player_state(game, config, p1.id)

        assert isinstance(resp, PlayerStateResponse)
        assert resp.hand_number == 1
        assert len(resp.your_cards) == 2
        assert resp.your_chips > 0
        assert resp.game_over is False
        assert resp.state_version == game.state_version
        assert len(resp.players) == 2

    def test_player_sees_own_cards(self):
        game = Game()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        game.start()
        config = _default_config()

        resp1 = build_poker_player_state(game, config, p1.id)
        resp2 = build_poker_player_state(game, config, p2.id)

        # Both see 2 cards each
        assert len(resp1.your_cards) == 2
        assert len(resp2.your_cards) == 2
        # Different cards (with overwhelming probability)
        # Just verify the structure
        assert all(isinstance(c, str) for c in resp1.your_cards)

    def test_no_active_hand_returns_complete(self):
        """When current_hand is None (between hands), returns 'complete' phase."""
        game = Game()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        game.start()
        config = _default_config()

        # Force current_hand to None (simulating a game-over-like state)
        game.current_hand = None

        resp = build_poker_player_state(game, config, p1.id)
        assert resp.phase == "complete"
        assert resp.your_cards == []
        assert resp.pot == 0

    def test_is_your_turn(self):
        game = Game()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        game.start()
        config = _default_config()

        hand = game.current_hand
        assert hand is not None
        cp = hand.current_player
        assert cp is not None

        resp_current = build_poker_player_state(game, config, cp.id)
        other_id = p1.id if cp.id != p1.id else p2.id
        resp_other = build_poker_player_state(game, config, other_id)

        assert resp_current.is_your_turn is True
        assert resp_other.is_your_turn is False
        assert resp_current.current_turn == cp.id
        assert resp_other.current_turn == cp.id

    def test_chat_log_included(self):
        game = Game()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        game.start()
        game.add_chat("Alice", "Hello!")
        config = _default_config()

        resp = build_poker_player_state(game, config, p1.id)
        assert len(resp.chat_log) == 1
        assert resp.chat_log[0].player == "Alice"
        assert resp.chat_log[0].message == "Hello!"

    def test_seed_commitment(self):
        game = Game()
        game.register("Alice")
        game.register("Bob")
        game.start()
        config = _default_config()

        resp = build_poker_player_state(game, config, 1)
        assert resp.seed_commitment == game.seed_commitment
        assert resp.seed_commitment != ""


# ── Dice spectator ───────────────────────────────────────


class TestBuildDiceSpectatorState:
    def test_before_start(self):
        game = DiceGame()
        game.register("Alice")
        game.register("Bob")
        config = _default_config()

        resp = build_dice_spectator_state(game, config)

        assert isinstance(resp, DiceSpectatorResponse)
        assert resp.started is False
        assert resp.game_over is False
        assert len(resp.players) == 2
        assert resp.last_dice is None
        assert resp.state_version == 0

    def test_during_betting(self):
        game = DiceGame()
        game.register("Alice")
        game.register("Bob")
        game.start()
        config = _default_config()

        resp = build_dice_spectator_state(game, config)

        assert resp.started is True
        assert resp.phase == "betting"
        assert resp.round_number == 1
        assert resp.ante == game.ante
        assert len(resp.players) == 2

    def test_overrides_applied(self):
        game = DiceGame()
        game.register("Alice")
        game.register("Bob")
        config = _default_config()

        resp = build_dice_spectator_state(
            game, config,
            commentary_text="Dice roll incoming!",
            stream_id=99,
        )
        assert resp.commentary_text == "Dice roll incoming!"
        assert resp.stream_id == 99

    def test_after_round_complete(self):
        game = DiceGame()
        game.register("Alice")
        game.register("Bob")
        game.start()
        config = _default_config()

        # Play through one round: both players bet
        cp = game.current_player
        assert cp is not None
        game.do_action(cp.id, "high")

        cp2 = game.current_player
        assert cp2 is not None
        game.do_action(cp2.id, "low")

        # Round should have resolved
        resp = build_dice_spectator_state(game, config)
        assert resp.started is True
        # After resolution, last_dice should be set
        assert resp.last_dice is not None
        assert len(resp.last_dice) == 2


# ── Dice player state ────────────────────────────────────


class TestBuildDicePlayerState:
    def test_during_betting(self):
        game = DiceGame()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        game.start()
        config = _default_config()

        resp = build_dice_player_state(game, config, p1.id)

        assert isinstance(resp, DiceStateResponse)
        assert resp.started is True
        assert resp.your_player_id == p1.id
        assert resp.your_chips > 0
        assert resp.phase == "betting"
        assert resp.round_number == 1

    def test_is_your_turn(self):
        game = DiceGame()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        game.start()
        config = _default_config()

        cp = game.current_player
        assert cp is not None

        resp_current = build_dice_player_state(game, config, cp.id)
        other_id = p1.id if cp.id != p1.id else p2.id
        resp_other = build_dice_player_state(game, config, other_id)

        assert resp_current.is_your_turn is True
        assert resp_other.is_your_turn is False

    def test_extensions_remaining(self):
        game = DiceGame()
        p1 = game.register("Alice")
        p2 = game.register("Bob")
        game.start()
        config = _default_config()

        resp = build_dice_player_state(game, config, p1.id)
        assert resp.extensions_remaining == game.get_extensions_remaining(p1.id)

    def test_chat_included(self):
        game = DiceGame()
        p1 = game.register("Alice")
        game.register("Bob")
        game.start()
        game.add_chat("Alice", "Rolling!")
        config = _default_config()

        resp = build_dice_player_state(game, config, p1.id)
        assert len(resp.chat) == 1
        assert resp.chat[0]["player"] == "Alice"
        assert resp.chat[0]["message"] == "Rolling!"

    def test_seed_commitment(self):
        game = DiceGame()
        game.register("Alice")
        game.register("Bob")
        game.start()
        config = _default_config()

        resp = build_dice_player_state(game, config, 1)
        assert resp.seed_commitment == game.seed_commitment
        assert resp.seed_commitment != ""
