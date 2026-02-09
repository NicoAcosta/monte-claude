from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Stream:
    id: int
    game_id: int
    host_username: str
    title: str
    commentary_text: str | None = None
    created_at: float = field(default_factory=time.time)
