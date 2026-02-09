from __future__ import annotations

from psycopg_pool import ConnectionPool

from core.history_models import GameEvent, PlayerStats


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
            hands_won=row[3], total_winnings=row[4], biggest_pot_won=int(row[5]),
        )

    def get_all(self, limit: int = 50, offset: int = 0) -> list[PlayerStats]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT username, games_played, hands_played, hands_won, "
                "total_winnings, biggest_pot_won FROM player_stats "
                "ORDER BY total_winnings DESC LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()
        return [
            PlayerStats(
                username=r[0], games_played=r[1], hands_played=r[2],
                hands_won=r[3], total_winnings=r[4], biggest_pot_won=int(r[5]),
            )
            for r in rows
        ]

    def count_all(self) -> int:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM player_stats").fetchone()
        return row[0] if row else 0

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
        token_symbol: str = "chips",
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
                        hands_won=row[2], total_winnings=row[3], biggest_pot_won=int(row[4]),
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

                # Per-token stats
                conn.execute(
                    """INSERT INTO player_token_stats
                       (username, token_symbol, total_winnings, biggest_pot_won, hands_played, hands_won)
                       VALUES (%s, %s, %s, %s, 1, %s)
                       ON CONFLICT (username, token_symbol) DO UPDATE SET
                       total_winnings = player_token_stats.total_winnings + EXCLUDED.total_winnings,
                       biggest_pot_won = GREATEST(player_token_stats.biggest_pot_won, EXCLUDED.biggest_pot_won),
                       hands_played = player_token_stats.hands_played + 1,
                       hands_won = player_token_stats.hands_won + EXCLUDED.hands_won""",
                    (name, token_symbol, delta, pot_won, 1 if won else 0),
                )
            conn.commit()

    def get_token_stats(self, username: str) -> list[dict]:
        """Return per-token winnings for a player."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT token_symbol, total_winnings, biggest_pot_won, hands_played, hands_won "
                "FROM player_token_stats WHERE username = %s ORDER BY total_winnings DESC",
                (username,),
            ).fetchall()
        return [
            {
                "token_symbol": r[0],
                "total_winnings": int(r[1]),
                "biggest_pot_won": int(r[2]),
                "hands_played": r[3],
                "hands_won": r[4],
            }
            for r in rows
        ]

    def get_all_token_stats(self) -> dict[str, list[dict]]:
        """Return per-token winnings for all players, keyed by username."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT username, token_symbol, total_winnings, biggest_pot_won, hands_played, hands_won "
                "FROM player_token_stats ORDER BY username, total_winnings DESC",
            ).fetchall()
        result: dict[str, list[dict]] = {}
        for r in rows:
            entry = {
                "token_symbol": r[1],
                "total_winnings": int(r[2]),
                "biggest_pot_won": int(r[3]),
                "hands_played": r[4],
                "hands_won": r[5],
            }
            result.setdefault(r[0], []).append(entry)
        return result

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
