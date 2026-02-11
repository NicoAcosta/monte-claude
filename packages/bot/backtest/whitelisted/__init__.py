"""Auto-discovers whitelisted strategies, ready for HTTP play.

Usage:
    from backtest.whitelisted import WHITELISTED

    # WHITELISTED = {"viper": (decide_fn, reset_fn), ...}
    # Use with bot.__main__ or directly with the game client.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent

WHITELISTED: dict[str, tuple] = {}

for _path in sorted(_DIR.glob("*.py")):
    if _path.name == "__init__.py":
        continue
    try:
        _name = _path.stem
        _mod_name = f"whitelisted_{_name}"
        _spec = importlib.util.spec_from_file_location(_mod_name, _path)
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[_mod_name] = _mod
        _spec.loader.exec_module(_mod)
        if hasattr(_mod, "decide") and hasattr(_mod, "reset_tracker"):
            WHITELISTED[_name.lower()] = (_mod.decide, _mod.reset_tracker)
    except Exception:
        pass  # Skip broken files silently at import time
