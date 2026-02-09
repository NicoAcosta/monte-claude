from __future__ import annotations

import json

from psycopg_pool import ConnectionPool

from poker.history_models import GameEvent, HandSummary, PlayerStats


class GameEventStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def append(self, event: GameEvent) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO game_events (game_id, event_type, timestamp, hand_number, data, sequence)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (event.game_id, event.event_type, event.timestamp,
                 event.hand_number, event.data, event.sequence),
            )
            conn.commit()

    def get_by_game(self, game_id: int) -> list[GameEvent]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT game_id, event_type, timestamp, hand_number, data, sequence "
                "FROM game_events WHERE game_id = %s ORDER BY sequence",
                (game_id,),
            ).fetchall()
        return [
            GameEvent(
                game_id=r[0], event_type=r[1], timestamp=r[2],
                hand_number=r[3], data=r[4], sequence=r[5],
            )
            for r in rows
        ]


class HandSummaryStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def append(self, summary: HandSummary) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO hand_summaries
                   (game_id, hand_number, dealer_id, player_ids, winner_ids, pot, community_cards, timestamp)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (summary.game_id, summary.hand_number, summary.dealer_id,
                 json.dumps(list(summary.player_ids)),
                 json.dumps(list(summary.winner_ids)),
                 summary.pot, summary.community_cards, summary.timestamp),
            )
            conn.commit()

    def get_by_game(self, game_id: int) -> list[HandSummary]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT game_id, hand_number, dealer_id, player_ids, winner_ids, "
                "pot, community_cards, timestamp "
                "FROM hand_summaries WHERE game_id = %s ORDER BY hand_number",
                (game_id,),
            ).fetchall()
        return [
            HandSummary(
                game_id=r[0], hand_number=r[1], dealer_id=r[2],
                player_ids=tuple(json.loads(r[3])),
                winner_ids=tuple(json.loads(r[4])),
                pot=r[5], community_cards=r[6], timestamp=r[7],
            )
            for r in rows
        ]


class PlayerStatsStore:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get(self, username: str) -> PlayerStats | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT username, games_played, hands_played, hands_won, "
                "total_winnings, biggest_pot_won FROM player_stats WHERE username = %s",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return PlayerStats(
            username=row[0], games_played=row[1], hands_played=row[2],
            hands_won=row[3], total_winnings=row[4], biggest_pot_won=row[5],
        )

    def update(self, stats: PlayerStats) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO player_stats
                   (username, games_played, hands_played, hands_won, total_winnings, biggest_pot_won)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (username) DO UPDATE SET
                   games_played = EXCLUDED.games_played,
                   hands_played = EXCLUDED.hands_played,
                   hands_won = EXCLUDED.hands_won,
                   total_winnings = EXCLUDED.total_winnings,
                   biggest_pot_won = EXCLUDED.biggest_pot_won""",
                (stats.username, stats.games_played, stats.hands_played,
                 stats.hands_won, stats.total_winnings, stats.biggest_pot_won),
            )
            conn.commit()

    def update_from_hand(
        self,
        player_names: list[str],
        winner_names: list[str],
        pot: int,
        chip_deltas: dict[str, int],
    ) -> None:
        with self._pool.connection() as conn:
            for name in player_names:
                row = conn.execute(
                    "SELECT games_played, hands_played, hands_won, "
                    "total_winnings, biggest_pot_won "
                    "FROM player_stats WHERE username = %s FOR UPDATE",
                    (name,),
                ).fetchone()

                if row is None:
                    current = PlayerStats(
                        username=name, games_played=0, hands_played=0,
                        hands_won=0, total_winnings=0, biggest_pot_won=0,
                    )
                else:
                    current = PlayerStats(
                        username=name, games_played=row[0], hands_played=row[1],
                        hands_won=row[2], total_winnings=row[3], biggest_pot_won=row[4],
                    )

                won = name in winner_names
                delta = chip_deltas.get(name, 0)
                pot_won = pot // len(winner_names) if won else 0

                updated = PlayerStats(
                    username=name,
                    games_played=current.games_played,
                    hands_played=current.hands_played + 1,
                    hands_won=current.hands_won + (1 if won else 0),
                    total_winnings=current.total_winnings + delta,
                    biggest_pot_won=max(current.biggest_pot_won, pot_won),
                )

                conn.execute(
                    """INSERT INTO player_stats
                       (username, games_played, hands_played, hands_won, total_winnings, biggest_pot_won)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (username) DO UPDATE SET
                       games_played = EXCLUDED.games_played,
                       hands_played = EXCLUDED.hands_played,
                       hands_won = EXCLUDED.hands_won,
                       total_winnings = EXCLUDED.total_winnings,
                       biggest_pot_won = EXCLUDED.biggest_pot_won""",
                    (updated.username, updated.games_played, updated.hands_played,
                     updated.hands_won, updated.total_winnings, updated.biggest_pot_won),
                )
            conn.commit()

    def increment_games_played(self, usernames: list[str]) -> None:
        with self._pool.connection() as conn:
            for name in usernames:
                conn.execute(
                    """INSERT INTO player_stats
                       (username, games_played, hands_played, hands_won, total_winnings, biggest_pot_won)
                       VALUES (%s, 1, 0, 0, 0, 0)
                       ON CONFLICT (username) DO UPDATE
                       SET games_played = player_stats.games_played + 1""",
                    (name,),
                )
            conn.commit()
