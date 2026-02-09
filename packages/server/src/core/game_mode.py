from __future__ import annotations

from enum import Enum


class GameMode(str, Enum):
    OFFCHAIN = "offchain"
    ONCHAIN = "onchain"
