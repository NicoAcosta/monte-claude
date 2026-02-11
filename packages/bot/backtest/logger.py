"""Hand-by-hand JSONL logger for backtest runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .engine import GameResult

RESULTS_DIR = Path(__file__).resolve().parent / "results"


class BacktestLogger:
    """Writes game/hand results to a JSONL file in results/."""

    def __init__(self, bot_names: list[str]) -> None:
        RESULTS_DIR.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tag = "_".join(sorted(n.lower() for n in bot_names))
        self.path = RESULTS_DIR / f"{ts}_{tag}.jsonl"
        self._file = open(self.path, "a")  # noqa: SIM115

    def log_game(self, result: GameResult) -> None:
        """Write all hand logs from a completed game."""
        for hand in result.hand_logs:
            record = {
                "game": result.game_number,
                "hand": hand.hand_number,
                "players": hand.players_cards,
                "community": hand.community_cards,
                "actions": hand.actions,
                "winners": hand.winners,
                "pot": hand.pot,
            }
            self._file.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()
