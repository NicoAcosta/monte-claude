"""Generic round summary store — writes to round_summaries table."""

from __future__ import annotations

import json
from dataclasses import dataclass

from psycopg_pool import ConnectionPool


@dataclass(frozen=True)
class RoundSummary:
    game_id: int
    game_type: str
    round_number: int
    player_ids: tuple[int, ...]
    winner_ids: tuple[int, ...]
    pot: int
    details: dict
    timestamp: float


class RoundSummaryStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def append(self, summary: RoundSummary) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO round_summaries
                   (game_id, game_type, round_number, player_ids, winner_ids, pot, details, timestamp)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (game_id, game_type, round_number) DO NOTHING""",
                (
                    summary.game_id,
                    summary.game_type,
                    summary.round_number,
                    list(summary.player_ids),
                    list(summary.winner_ids),
                    summary.pot,
                    json.dumps(summary.details),
                    summary.timestamp,
                ),
            )
            conn.commit()

    def get_by_game(self, game_id: int) -> list[RoundSummary]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """SELECT game_id, game_type, round_number, player_ids, winner_ids,
                          pot, details, timestamp
                   FROM round_summaries
                   WHERE game_id = %s
                   ORDER BY round_number""",
                (game_id,),
            ).fetchall()
        return [
            RoundSummary(
                game_id=r[0],
                game_type=r[1],
                round_number=r[2],
                player_ids=tuple(r[3]) if r[3] else (),
                winner_ids=tuple(r[4]) if r[4] else (),
                pot=r[5],
                details=r[6] if isinstance(r[6], dict) else json.loads(r[6]),
                timestamp=r[7],
            )
            for r in rows
        ]
