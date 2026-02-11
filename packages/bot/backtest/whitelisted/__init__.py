"""Auto-discovers whitelisted strategies, ready for HTTP play.

Usage:
    from backtest.whitelisted import WHITELISTED

    # WHITELISTED = {"viper": (decide_fn, reset_fn), ...}
    # Use with bot.__main__ or directly with the game client.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_log = logging.getLogger(__name__)

WHITELISTED: dict[str, tuple] = {}

for _path in sorted(_DIR.glob("*.py")):
    if _path.name == "__init__.py":
        continue
    _name = _path.stem
    _mod_name = f"whitelisted_{_name}"
    try:
        _spec = importlib.util.spec_from_file_location(_mod_name, _path)
        if _spec is None or _spec.loader is None:
            _log.warning("Cannot load whitelisted strategy %s: invalid module spec", _path.name)
            continue
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[_mod_name] = _mod
        _spec.loader.exec_module(_mod)
        if hasattr(_mod, "decide") and hasattr(_mod, "reset_tracker"):
            WHITELISTED[_name.lower()] = (_mod.decide, _mod.reset_tracker)
        else:
            _log.warning("Skipping %s: missing decide() or reset_tracker()", _path.name)
    except Exception:
        _log.warning("Failed to load whitelisted strategy %s", _path.name, exc_info=True)
    finally:
        sys.modules.pop(_mod_name, None)
