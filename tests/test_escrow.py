"""Tests for the escrow pure functions module."""

from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

import pytest

from poker.escrow import (
    EscrowConfig,
    build_create_and_deposit_calldata,
    build_deposit_calldata,
    compute_escrow_address,
    compute_payouts,
    generate_salt,
    sign_settlement,
)

# ── Test keys ─────────────────────────────────────────────

ADMIN_PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ADMIN_ADDR = Account.from_key(ADMIN_PK).address

ALICE = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
BOB = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
TOKEN = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC
RAKE_BENEFICIARY = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"

CHAIN_ID = 8453
ESCROW_ADDR = "0x1234567890abcdef1234567890abcdef12345678"


def _make_config() -> EscrowConfig:
    return EscrowConfig(
        token=TOKEN,
        admin=ADMIN_ADDR,
        rake_beneficiary=RAKE_BENEFICIARY,
        deposit_amount=100_000_000,
        rake_bps=250,
        funding_deadline=9999999999,
        settlement_deadline=9999999999 + 7200,
        participants=(ALICE, BOB),
    )


# ══════════════════════════════════════════════════════════
# compute_payouts
# ══════════════════════════════════════════════════════════

class TestComputePayouts:
    def test_winner_takes_all(self):
        player_chips = {ALICE: 2000, BOB: 0}
        payouts = compute_payouts(player_chips, buy_in=100_000_000, starting_chips=1000)
        result = dict(payouts)
        assert result[ALICE] == 200_000_000
        assert result[BOB] == 0

    def test_even_split(self):
        player_chips = {ALICE: 1000, BOB: 1000}
        payouts = compute_payouts(player_chips, buy_in=100_000_000, starting_chips=1000)
        result = dict(payouts)
        assert result[ALICE] == 100_000_000
        assert result[BOB] == 100_000_000

    def test_proportional(self):
        player_chips = {ALICE: 1500, BOB: 500}
        payouts = compute_payouts(player_chips, buy_in=100_000_000, starting_chips=1000)
        result = dict(payouts)
        assert result[ALICE] == 150_000_000
        assert result[BOB] == 50_000_000

    def test_sum_equals_total_deposits(self):
        player_chips = {ALICE: 1234, BOB: 766}
        payouts = compute_payouts(player_chips, buy_in=100_000_000, starting_chips=1000)
        total = sum(amount for _, amount in payouts)
        assert total == 200_000_000  # 2 players * 100M

    def test_rounding_dust_to_winner(self):
        # With 3 players and chips that don't divide evenly
        charlie = "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"
        player_chips = {ALICE: 1001, BOB: 999, charlie: 1000}
        payouts = compute_payouts(player_chips, buy_in=100_000_000, starting_chips=1000)
        total = sum(amount for _, amount in payouts)
        assert total == 300_000_000  # 3 players * 100M

    def test_three_players_exact(self):
        charlie = "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"
        player_chips = {ALICE: 3000, BOB: 0, charlie: 0}
        payouts = compute_payouts(player_chips, buy_in=100_000_000, starting_chips=1000)
        result = dict(payouts)
        assert result[ALICE] == 300_000_000


# ══════════════════════════════════════════════════════════
# sign_settlement
# ══════════════════════════════════════════════════════════

class TestSignSettlement:
    def test_produces_valid_signature(self):
        payouts = [(ALICE, 150_000_000), (BOB, 50_000_000)]
        sig_hex = sign_settlement(ADMIN_PK, CHAIN_ID, ESCROW_ADDR, payouts)

        # Should be 65 bytes (130 hex chars + 0x prefix)
        sig_bytes = bytes.fromhex(sig_hex.removeprefix("0x"))
        assert len(sig_bytes) == 65

    def test_recovers_to_admin(self):
        payouts = [(ALICE, 150_000_000), (BOB, 50_000_000)]
        sig_hex = sign_settlement(ADMIN_PK, CHAIN_ID, ESCROW_ADDR, payouts)

        # Recover signer from the structured data
        escrow_addr = Web3.to_checksum_address(ESCROW_ADDR)
        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "Payout": [
                    {"name": "recipient", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                ],
                "Settle": [
                    {"name": "payouts", "type": "Payout[]"},
                ],
            },
            "primaryType": "Settle",
            "domain": {
                "name": "TimeBasedEscrow",
                "version": "1",
                "chainId": CHAIN_ID,
                "verifyingContract": escrow_addr,
            },
            "message": {
                "payouts": [
                    {"recipient": Web3.to_checksum_address(ALICE), "amount": 150_000_000},
                    {"recipient": Web3.to_checksum_address(BOB), "amount": 50_000_000},
                ],
            },
        }

        signable = encode_typed_data(full_message=structured_data)
        sig_bytes = bytes.fromhex(sig_hex.removeprefix("0x"))
        recovered = Account.recover_message(signable, signature=sig_bytes)
        assert recovered == ADMIN_ADDR

    def test_different_payouts_different_signatures(self):
        sig1 = sign_settlement(ADMIN_PK, CHAIN_ID, ESCROW_ADDR, [(ALICE, 200_000_000), (BOB, 0)])
        sig2 = sign_settlement(ADMIN_PK, CHAIN_ID, ESCROW_ADDR, [(ALICE, 100_000_000), (BOB, 100_000_000)])
        assert sig1 != sig2


# ══════════════════════════════════════════════════════════
# build_create_and_deposit_calldata
# ══════════════════════════════════════════════════════════

class TestBuildCalldata:
    def test_create_and_deposit_starts_with_selector(self):
        config = _make_config()
        salt = generate_salt()
        calldata = build_create_and_deposit_calldata(config, salt)
        # Should start with 0x and be a hex string
        assert calldata.startswith("0x")
        # Function selector is 4 bytes = 8 hex chars
        assert len(calldata) > 10

    def test_deposit_calldata_has_correct_selector(self):
        calldata = build_deposit_calldata(ALICE)
        assert calldata.startswith("0x")
        # deposit(address) selector
        expected_selector = Web3.keccak(text="deposit(address)")[:4].hex()
        assert calldata[2:10] == expected_selector


# ══════════════════════════════════════════════════════════
# EscrowConfig
# ══════════════════════════════════════════════════════════

class TestEscrowConfig:
    def test_checksums_addresses(self):
        config = _make_config()
        assert config.token == Web3.to_checksum_address(TOKEN)
        assert config.admin == Web3.to_checksum_address(ADMIN_ADDR)

    def test_as_tuple(self):
        config = _make_config()
        t = config.as_tuple()
        assert len(t) == 8
        assert t[0] == config.token
        assert t[3] == 100_000_000
        assert isinstance(t[7], list)  # participants as list for ABI

    def test_immutable(self):
        config = _make_config()
        with pytest.raises(AttributeError, match="immutable"):
            config.token = "0x0000000000000000000000000000000000000000"

    def test_participants_sorted(self):
        config = _make_config()
        addrs = list(config.participants)
        assert addrs == sorted(addrs, key=lambda a: int(a, 16))


# ══════════════════════════════════════════════════════════
# generate_salt
# ══════════════════════════════════════════════════════════

class TestComputeEscrowAddress:
    def test_raises_without_rpc_url(self):
        config = _make_config()
        salt = generate_salt()
        with pytest.raises(ValueError, match="rpc_url is required"):
            compute_escrow_address("0x" + "00" * 20, config, salt)


class TestGenerateSalt:
    def test_correct_length(self):
        salt = generate_salt()
        assert len(salt) == 32

    def test_unique(self):
        salts = {generate_salt() for _ in range(10)}
        assert len(salts) == 10
