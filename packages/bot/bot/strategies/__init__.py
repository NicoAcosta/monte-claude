"""Advanced poker strategies for Monteclaude bots."""

from .shark import decide as shark_decide, reset_tracker as reset_shark
from .wolf import decide as wolf_decide, reset_tracker as reset_wolf
from .fox import decide as fox_decide, reset_tracker as reset_fox
from .hawk import decide as hawk_decide, reset_tracker as reset_hawk

STRATEGIES = {
    "shark": (shark_decide, reset_shark),
    "wolf": (wolf_decide, reset_wolf),
    "fox": (fox_decide, reset_fox),
    "hawk": (hawk_decide, reset_hawk),
}

__all__ = ["STRATEGIES", "shark_decide", "wolf_decide", "fox_decide", "hawk_decide"]
