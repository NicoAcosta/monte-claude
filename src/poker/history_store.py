from __future__ import annotations

import csv
import json
from pathlib import Path

from poker.history_models import GameEvent, HandSummary, PlayerStats


class GameEventStore:
    _CSV_HEADERS = ("game_id", "event_type", "timestamp", "hand_number", "data", "sequence")

    def __init__(self, csv_path: Path) -> None:
        self._csv_path = csv_path
        self._events: list[GameEvent] = []
        self._load()

    def _load(self) -> None:
        if not self._csv_path.exists():
            self._csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_headers()
            return
        with open(self._csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self._events.append(GameEvent(
                    game_id=int(row["game_id"]),
                    event_type=row["event_type"],
                    timestamp=float(row["timestamp"]),
                    hand_number=int(row["hand_number"]),
                    data=row["data"],
                    sequence=int(row["sequence"]),
                ))

    def _write_headers(self) -> None:
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self._CSV_HEADERS)

    def append(self, event: GameEvent) -> None:
        self._events.append(event)
        with open(self._csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow((
                event.game_id, event.event_type, event.timestamp,
                event.hand_number, event.data, event.sequence,
            ))

    def get_by_game(self, game_id: int) -> list[GameEvent]:
        return [e for e in self._events if e.game_id == game_id]


class HandSummaryStore:
    _CSV_HEADERS = (
        "game_id", "hand_number", "dealer_id", "player_ids",
        "winner_ids", "pot", "community_cards", "timestamp",
    )

    def __init__(self, csv_path: Path) -> None:
        self._csv_path = csv_path
        self._summaries: list[HandSummary] = []
        self._load()

    def _load(self) -> None:
        if not self._csv_path.exists():
            self._csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_headers()
            return
        with open(self._csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self._summaries.append(HandSummary(
                    game_id=int(row["game_id"]),
                    hand_number=int(row["hand_number"]),
                    dealer_id=int(row["dealer_id"]),
                    player_ids=tuple(json.loads(row["player_ids"])),
                    winner_ids=tuple(json.loads(row["winner_ids"])),
                    pot=int(row["pot"]),
                    community_cards=row["community_cards"],
                    timestamp=float(row["timestamp"]),
                ))

    def _write_headers(self) -> None:
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self._CSV_HEADERS)

    def append(self, summary: HandSummary) -> None:
        self._summaries.append(summary)
        with open(self._csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow((
                summary.game_id, summary.hand_number, summary.dealer_id,
                json.dumps(list(summary.player_ids)),
                json.dumps(list(summary.winner_ids)),
                summary.pot, summary.community_cards, summary.timestamp,
            ))

    def get_by_game(self, game_id: int) -> list[HandSummary]:
        return [s for s in self._summaries if s.game_id == game_id]


class PlayerStatsStore:
    _CSV_HEADERS = (
        "username", "games_played", "hands_played",
        "hands_won", "total_winnings", "biggest_pot_won",
    )

    def __init__(self, csv_path: Path) -> None:
        self._csv_path = csv_path
        self._stats: dict[str, PlayerStats] = {}
        self._load()

    def _load(self) -> None:
        if not self._csv_path.exists():
            self._csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_headers()
            return
        with open(self._csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats = PlayerStats(
                    username=row["username"],
                    games_played=int(row["games_played"]),
                    hands_played=int(row["hands_played"]),
                    hands_won=int(row["hands_won"]),
                    total_winnings=int(row["total_winnings"]),
                    biggest_pot_won=int(row["biggest_pot_won"]),
                )
                self._stats[stats.username] = stats

    def _write_headers(self) -> None:
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self._CSV_HEADERS)

    def get(self, username: str) -> PlayerStats | None:
        return self._stats.get(username)

    def update(self, stats: PlayerStats) -> None:
        self._stats[stats.username] = stats
        self._rewrite()

    def _rewrite(self) -> None:
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self._CSV_HEADERS)
            for s in self._stats.values():
                writer.writerow((
                    s.username, s.games_played, s.hands_played,
                    s.hands_won, s.total_winnings, s.biggest_pot_won,
                ))

    def update_from_hand(
        self,
        player_names: list[str],
        winner_names: list[str],
        pot: int,
        chip_deltas: dict[str, int],
    ) -> None:
        """Update stats for all players in a completed hand.

        Args:
            player_names: all players in the hand
            winner_names: names of players who won
            pot: total pot size
            chip_deltas: {username: net_chips_change} for each player
        """
        for name in player_names:
            current = self._stats.get(name)
            if current is None:
                current = PlayerStats(
                    username=name, games_played=0, hands_played=0,
                    hands_won=0, total_winnings=0, biggest_pot_won=0,
                )

            won = name in winner_names
            delta = chip_deltas.get(name, 0)
            pot_won = pot // len(winner_names) if won else 0

            self._stats[name] = PlayerStats(
                username=name,
                games_played=current.games_played,
                hands_played=current.hands_played + 1,
                hands_won=current.hands_won + (1 if won else 0),
                total_winnings=current.total_winnings + delta,
                biggest_pot_won=max(current.biggest_pot_won, pot_won),
            )
        self._rewrite()

    def increment_games_played(self, usernames: list[str]) -> None:
        """Increment games_played counter for a list of players."""
        for name in usernames:
            current = self._stats.get(name)
            if current is None:
                current = PlayerStats(
                    username=name, games_played=0, hands_played=0,
                    hands_won=0, total_winnings=0, biggest_pot_won=0,
                )
            self._stats[name] = PlayerStats(
                username=name,
                games_played=current.games_played + 1,
                hands_played=current.hands_played,
                hands_won=current.hands_won,
                total_winnings=current.total_winnings,
                biggest_pot_won=current.biggest_pot_won,
            )
        self._rewrite()
