"""Tests for per-round commit-reveal provable fairness."""

import hashlib

import pytest

from core.fairness import FairRng, SeedCommitment, generate_seed, verify_seed
from poker.deck import Deck


class TestGenerateSeed:
    def test_returns_seed_commitment(self):
        sc = generate_seed()
        assert isinstance(sc, SeedCommitment)

    def test_seed_hex_is_64_chars(self):
        sc = generate_seed()
        assert len(sc.seed_hex) == 64
        # Verify it's valid hex
        int(sc.seed_hex, 16)

    def test_commitment_is_sha256_of_seed(self):
        sc = generate_seed()
        expected = hashlib.sha256(bytes.fromhex(sc.seed_hex)).hexdigest()
        assert sc.commitment == expected

    def test_two_seeds_differ(self):
        a = generate_seed()
        b = generate_seed()
        assert a.seed_hex != b.seed_hex
        assert a.commitment != b.commitment

    def test_frozen_dataclass(self):
        sc = generate_seed()
        with pytest.raises(AttributeError):
            sc.seed_hex = "00" * 32  # type: ignore[misc]

    def test_rejects_short_seed_hex(self):
        with pytest.raises(ValueError, match="64 lowercase hex"):
            SeedCommitment(seed_hex="abcd", commitment="00" * 32)

    def test_rejects_uppercase_seed_hex(self):
        with pytest.raises(ValueError, match="64 lowercase hex"):
            SeedCommitment(seed_hex="AA" * 32, commitment="00" * 32)

    def test_rejects_bad_commitment(self):
        with pytest.raises(ValueError, match="64 lowercase hex"):
            SeedCommitment(seed_hex="00" * 32, commitment="short")


class TestVerifySeed:
    def test_correct_seed_returns_true(self):
        sc = generate_seed()
        assert verify_seed(sc.seed_hex, sc.commitment) is True

    def test_wrong_seed_returns_false(self):
        sc = generate_seed()
        assert verify_seed("00" * 32, sc.commitment) is False

    def test_wrong_commitment_returns_false(self):
        sc = generate_seed()
        assert verify_seed(sc.seed_hex, "00" * 64) is False


class TestFairRng:
    """HMAC-DRBG (NIST SP 800-90A) deterministic RNG."""

    def test_deterministic(self):
        seed = b'\x42' * 32
        r1 = FairRng(seed)
        r2 = FairRng(seed)
        assert r1.generate(32) == r2.generate(32)

    def test_different_seeds_differ(self):
        r1 = FairRng(b'\x01' * 32)
        r2 = FairRng(b'\x02' * 32)
        assert r1.generate(32) != r2.generate(32)

    def test_randbelow_range(self):
        rng = FairRng(b'\x00' * 32)
        for _ in range(100):
            v = rng.randbelow(6)
            assert 0 <= v < 6

    def test_shuffle_permutation(self):
        rng = FairRng(b'\x00' * 32)
        items = list(range(52))
        rng.shuffle(items)
        assert sorted(items) == list(range(52))
        assert items != list(range(52))  # extremely unlikely to be identity


class TestDeckReplay:
    """Same seed → same Deck card order → verifiable."""

    def test_same_seed_same_deck(self):
        sc = generate_seed()
        d1 = Deck(seed_hex=sc.seed_hex)
        d2 = Deck(seed_hex=sc.seed_hex)
        cards1 = d1.deal(5)
        cards2 = d2.deal(5)
        assert cards1 == cards2

    def test_different_seed_different_deck(self):
        a = generate_seed()
        b = generate_seed()
        d1 = Deck(seed_hex=a.seed_hex)
        d2 = Deck(seed_hex=b.seed_hex)
        # Extremely unlikely to match
        assert d1.deal(5) != d2.deal(5)


class TestDiceReplay:
    """Same seed → same dice roll via FairRng."""

    def test_same_seed_same_dice(self):
        sc = generate_seed()
        seed_bytes = bytes.fromhex(sc.seed_hex)
        rng1 = FairRng(seed_bytes)
        rng2 = FairRng(seed_bytes)
        dice1 = (1 + rng1.randbelow(6), 1 + rng1.randbelow(6))
        dice2 = (1 + rng2.randbelow(6), 1 + rng2.randbelow(6))
        assert dice1 == dice2

    def test_different_seed_different_dice(self):
        a = generate_seed()
        b = generate_seed()
        rng1 = FairRng(bytes.fromhex(a.seed_hex))
        rng2 = FairRng(bytes.fromhex(b.seed_hex))
        # Run enough times that at least one pair differs
        results1 = [(1 + rng1.randbelow(6), 1 + rng1.randbelow(6)) for _ in range(10)]
        results2 = [(1 + rng2.randbelow(6), 1 + rng2.randbelow(6)) for _ in range(10)]
        assert results1 != results2
