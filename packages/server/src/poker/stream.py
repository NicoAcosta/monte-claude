from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Stream:
    id: int
    game_id: int
    host_username: str
    title: str
    commentary_text: str | None = None
