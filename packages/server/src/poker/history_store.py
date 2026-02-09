from __future__ import annotations

import json

from psycopg_pool import ConnectionPool

from poker.history_models import HandSummary

# Re-export from core for backward compatibility
from core.history_store import GameEventStore, PlayerStatsStore  # noqa: F401


class HandSummaryStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def append(self, summary: HandSummary) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO hand_summaries
                   (game_id, hand_number, dealer_id, player_ids, winner_ids, pot,
                    community_cards, timestamp, winner_names, winning_cards, result_type,
                    token_symbol)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (summary.game_id, summary.hand_number, summary.dealer_id,
                 json.dumps(list(summary.player_ids)),
                 json.dumps(list(summary.winner_ids)),
                 summary.pot, summary.community_cards, summary.timestamp,
                 json.dumps(list(summary.winner_names)),
                 summary.winning_cards, summary.result_type,
                 summary.token_symbol),
            )
            conn.commit()

    _SUMMARY_COLS = (
        "game_id, hand_number, dealer_id, player_ids, winner_ids, "
        "pot, community_cards, timestamp, winner_names, winning_cards, "
        "result_type, token_symbol"
    )

    @staticmethod
    def _row_to_summary(r: tuple) -> HandSummary:
        return HandSummary(
            game_id=r[0], hand_number=r[1], dealer_id=r[2],
            player_ids=tuple(json.loads(r[3])),
            winner_ids=tuple(json.loads(r[4])),
            pot=r[5], community_cards=r[6], timestamp=r[7],
            winner_names=tuple(json.loads(r[8] or "[]")),
            winning_cards=r[9] or "{}",
            result_type=r[10] or "fold",
            token_symbol=r[11],
        )

    def get_by_game(self, game_id: int) -> list[HandSummary]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {self._SUMMARY_COLS} "
                "FROM hand_summaries WHERE game_id = %s ORDER BY hand_number",
                (game_id,),
            ).fetchall()
        return [self._row_to_summary(r) for r in rows]

    def get_recent(self, limit: int = 20, offset: int = 0) -> list[HandSummary]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {self._SUMMARY_COLS} "
                "FROM hand_summaries ORDER BY timestamp DESC LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()
        return [self._row_to_summary(r) for r in rows]

    def count_all(self) -> int:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM hand_summaries").fetchone()
        return row[0] if row else 0
