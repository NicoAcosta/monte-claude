"""Per-round commit-reveal for provable fairness.

Before each hand/round the server commits SHA-256(seed); after, it reveals
the seed so clients can replay the RNG and verify outcomes.

Verification spec (any language):
    1. seed_bytes = hex_decode(seed_hex)
    2. assert SHA-256(seed_bytes) == commitment
    3. rng = HMAC-DRBG(seed_bytes)  # NIST SP 800-90A, HMAC-SHA256
    4. Poker: Fisher-Yates shuffle ordered deck using rng.randbelow()
    5. Dice:  d1 = 1 + rng.randbelow(6), d2 = 1 + rng.randbelow(6)

HMAC-DRBG randbelow(n): generate(4 bytes) → uint32 big-endian → mod n.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import os
import re
from dataclasses import dataclass

_HEX64_RE = re.compile(r'^[0-9a-f]{64}$')


@dataclass(frozen=True)
class SeedCommitment:
    seed_hex: str   # 64-char hex — revealed after the round
    commitment: str  # SHA-256 hex digest of the raw seed bytes

    def __post_init__(self) -> None:
        if not _HEX64_RE.match(self.seed_hex):
            raise ValueError(f"seed_hex must be 64 lowercase hex chars, got {len(self.seed_hex)} chars")
        if not _HEX64_RE.match(self.commitment):
            raise ValueError(f"commitment must be 64 lowercase hex chars, got {len(self.commitment)} chars")


def generate_seed() -> SeedCommitment:
    """Generate a cryptographic seed with its SHA-256 commitment."""
    seed_bytes = os.urandom(32)
    return SeedCommitment(
        seed_hex=seed_bytes.hex(),
        commitment=hashlib.sha256(seed_bytes).hexdigest(),
    )


def verify_seed(seed_hex: str, commitment: str) -> bool:
    """Verify that a revealed seed matches a previously published commitment."""
    return _hmac.compare_digest(
        hashlib.sha256(bytes.fromhex(seed_hex)).hexdigest(),
        commitment,
    )


class FairRng:
    """HMAC-DRBG (NIST SP 800-90A, Section 10.1.2) with HMAC-SHA256.

    Deterministic and reproducible in any language implementing the spec.
    """

    def __init__(self, seed: bytes) -> None:
        self._k = b'\x00' * 32
        self._v = b'\x01' * 32
        self._update(seed)

    def _update(self, data: bytes = b'') -> None:
        """HMAC_DRBG_Update (Section 10.1.2.2)."""
        self._k = _hmac.new(self._k, self._v + b'\x00' + data, hashlib.sha256).digest()
        self._v = _hmac.new(self._k, self._v, hashlib.sha256).digest()
        if data:
            self._k = _hmac.new(self._k, self._v + b'\x01' + data, hashlib.sha256).digest()
            self._v = _hmac.new(self._k, self._v, hashlib.sha256).digest()

    def generate(self, num_bytes: int) -> bytes:
        """Generate pseudorandom bytes (Section 10.1.2.5)."""
        out = b''
        while len(out) < num_bytes:
            self._v = _hmac.new(self._k, self._v, hashlib.sha256).digest()
            out += self._v
        self._update()
        return out[:num_bytes]

    def randbelow(self, n: int) -> int:
        """Uniform random int in [0, n). Consumes 4 bytes per call."""
        raw = self.generate(4)
        return int.from_bytes(raw, 'big') % n

    def shuffle(self, items: list) -> None:
        """Fisher-Yates shuffle in-place."""
        for i in range(len(items) - 1, 0, -1):
            j = self.randbelow(i + 1)
            items[i], items[j] = items[j], items[i]
