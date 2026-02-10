"""Tests for the escrow pure functions module."""

from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

import pytest

from core.escrow import (
    EscrowConfig,
    build_approve_calldata,
    build_create_and_deposit_calldata,
    build_deposit_calldata,
    compute_escrow_address,
    compute_payouts,
    generate_salt,
    get_env_config,
    sign_create_escrow,
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
FACTORY_ADDR = "0x1111111111111111111111111111111111111111"


def _make_config(pcr0_hash: bytes = b"\x00" * 32) -> EscrowConfig:
    return EscrowConfig(
        token=TOKEN,
        admin=ADMIN_ADDR,
        rake_beneficiary=RAKE_BENEFICIARY,
        deposit_amount=100_000_000,
        rake_bps=250,
        funding_deadline=9999999999,
        settlement_deadline=9999999999 + 7200,
        participants=(ALICE, BOB),
        pcr0_hash=pcr0_hash,
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
                    {"name": "pcr0", "type": "bytes"},
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
                "pcr0": b"",
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
# sign_create_escrow
# ══════════════════════════════════════════════════════════

class TestSignCreateEscrow:
    def test_produces_valid_signature(self):
        config = _make_config()
        salt = generate_salt()
        sig_hex = sign_create_escrow(ADMIN_PK, CHAIN_ID, FACTORY_ADDR, config, salt)
        sig_bytes = bytes.fromhex(sig_hex.removeprefix("0x"))
        assert len(sig_bytes) == 65

    def test_recovers_to_admin(self):
        from eth_abi import encode as abi_encode

        config = _make_config()
        salt = generate_salt()
        sig_hex = sign_create_escrow(ADMIN_PK, CHAIN_ID, FACTORY_ADDR, config, salt)

        factory_addr = Web3.to_checksum_address(FACTORY_ADDR)
        # Solidity's abi.encodePacked(address[]) pads each element to 32 bytes
        participants_hash = Web3.keccak(
            b"".join(
                abi_encode(["address"], [addr]) for addr in config.participants
            )
        )

        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "CreateEscrow": [
                    {"name": "token", "type": "address"},
                    {"name": "admin", "type": "address"},
                    {"name": "rakeBeneficiary", "type": "address"},
                    {"name": "depositAmount", "type": "uint256"},
                    {"name": "rakeBps", "type": "uint16"},
                    {"name": "fundingDeadline", "type": "uint256"},
                    {"name": "settlementDeadline", "type": "uint256"},
                    {"name": "participantsHash", "type": "bytes32"},
                    {"name": "pcr0Hash", "type": "bytes32"},
                    {"name": "salt", "type": "bytes32"},
                ],
            },
            "primaryType": "CreateEscrow",
            "domain": {
                "name": "EscrowFactory",
                "version": "1",
                "chainId": CHAIN_ID,
                "verifyingContract": factory_addr,
            },
            "message": {
                "token": config.token,
                "admin": config.admin,
                "rakeBeneficiary": config.rake_beneficiary,
                "depositAmount": config.deposit_amount,
                "rakeBps": config.rake_bps,
                "fundingDeadline": config.funding_deadline,
                "settlementDeadline": config.settlement_deadline,
                "participantsHash": participants_hash,
                "pcr0Hash": config.pcr0_hash,
                "salt": salt,
            },
        }

        signable = encode_typed_data(full_message=structured_data)
        sig_bytes = bytes.fromhex(sig_hex.removeprefix("0x"))
        recovered = Account.recover_message(signable, signature=sig_bytes)
        assert recovered == ADMIN_ADDR

    def test_different_config_different_sig(self):
        config1 = _make_config()
        config2 = EscrowConfig(
            token=TOKEN,
            admin=ADMIN_ADDR,
            rake_beneficiary=RAKE_BENEFICIARY,
            deposit_amount=200_000_000,  # different
            rake_bps=250,
            funding_deadline=9999999999,
            settlement_deadline=9999999999 + 7200,
            participants=(ALICE, BOB),
        )
        salt = generate_salt()
        sig1 = sign_create_escrow(ADMIN_PK, CHAIN_ID, FACTORY_ADDR, config1, salt)
        sig2 = sign_create_escrow(ADMIN_PK, CHAIN_ID, FACTORY_ADDR, config2, salt)
        assert sig1 != sig2

    def test_different_salt_different_sig(self):
        config = _make_config()
        salt1 = b"\x01" * 32
        salt2 = b"\x02" * 32
        sig1 = sign_create_escrow(ADMIN_PK, CHAIN_ID, FACTORY_ADDR, config, salt1)
        sig2 = sign_create_escrow(ADMIN_PK, CHAIN_ID, FACTORY_ADDR, config, salt2)
        assert sig1 != sig2

    def test_different_factory_different_sig(self):
        config = _make_config()
        salt = generate_salt()
        factory1 = "0x1111111111111111111111111111111111111111"
        factory2 = "0x2222222222222222222222222222222222222222"
        sig1 = sign_create_escrow(ADMIN_PK, CHAIN_ID, factory1, config, salt)
        sig2 = sign_create_escrow(ADMIN_PK, CHAIN_ID, factory2, config, salt)
        assert sig1 != sig2

    def test_digest_matches_manual_solidity_computation(self):
        """Cross-validate: manual EIP-712 (matching Solidity abi.encode) == encode_typed_data.

        This mirrors EscrowFactory._hashCreateEscrow + _domainSeparator + _hashTypedData
        step by step, using eth_abi.encode to produce the same bytes as Solidity abi.encode.
        """
        from eth_abi import encode as abi_encode

        config = _make_config()
        salt = b"\xaa" * 32
        factory_addr = Web3.to_checksum_address(FACTORY_ADDR)

        # ── Domain separator (mirrors EscrowFactory._domainSeparator) ──
        domain_type_hash = Web3.keccak(
            text="EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
        )
        name_hash = Web3.keccak(text="EscrowFactory")
        version_hash = Web3.keccak(text="1")
        domain_sep = Web3.keccak(
            abi_encode(
                ["bytes32", "bytes32", "bytes32", "uint256", "address"],
                [domain_type_hash, name_hash, version_hash, CHAIN_ID, factory_addr],
            )
        )

        # ── Struct hash (mirrors EscrowFactory._hashCreateEscrow) ──
        create_type_hash = Web3.keccak(
            text=(
                "CreateEscrow(address token,address admin,address rakeBeneficiary,"
                "uint256 depositAmount,uint16 rakeBps,uint256 fundingDeadline,"
                "uint256 settlementDeadline,bytes32 participantsHash,"
                "bytes32 pcr0Hash,bytes32 salt)"
            )
        )
        # Solidity's abi.encodePacked(address[]) pads each element to 32 bytes
        participants_hash = Web3.keccak(
            b"".join(
                abi_encode(["address"], [addr]) for addr in config.participants
            )
        )
        struct_hash = Web3.keccak(
            abi_encode(
                [
                    "bytes32", "address", "address", "address",
                    "uint256", "uint16", "uint256", "uint256",
                    "bytes32", "bytes32", "bytes32",
                ],
                [
                    create_type_hash,
                    config.token,
                    config.admin,
                    config.rake_beneficiary,
                    config.deposit_amount,
                    config.rake_bps,
                    config.funding_deadline,
                    config.settlement_deadline,
                    participants_hash,
                    config.pcr0_hash,
                    salt,
                ],
            )
        )

        # ── Final digest (mirrors EscrowFactory._hashTypedData) ──
        manual_digest = Web3.keccak(b"\x19\x01" + domain_sep + struct_hash)

        # ── Library digest via encode_typed_data ──
        signable = encode_typed_data(
            full_message={
                "types": {
                    "EIP712Domain": [
                        {"name": "name", "type": "string"},
                        {"name": "version", "type": "string"},
                        {"name": "chainId", "type": "uint256"},
                        {"name": "verifyingContract", "type": "address"},
                    ],
                    "CreateEscrow": [
                        {"name": "token", "type": "address"},
                        {"name": "admin", "type": "address"},
                        {"name": "rakeBeneficiary", "type": "address"},
                        {"name": "depositAmount", "type": "uint256"},
                        {"name": "rakeBps", "type": "uint16"},
                        {"name": "fundingDeadline", "type": "uint256"},
                        {"name": "settlementDeadline", "type": "uint256"},
                        {"name": "participantsHash", "type": "bytes32"},
                        {"name": "pcr0Hash", "type": "bytes32"},
                        {"name": "salt", "type": "bytes32"},
                    ],
                },
                "primaryType": "CreateEscrow",
                "domain": {
                    "name": "EscrowFactory",
                    "version": "1",
                    "chainId": CHAIN_ID,
                    "verifyingContract": factory_addr,
                },
                "message": {
                    "token": config.token,
                    "admin": config.admin,
                    "rakeBeneficiary": config.rake_beneficiary,
                    "depositAmount": config.deposit_amount,
                    "rakeBps": config.rake_bps,
                    "fundingDeadline": config.funding_deadline,
                    "settlementDeadline": config.settlement_deadline,
                    "participantsHash": participants_hash,
                    "pcr0Hash": config.pcr0_hash,
                    "salt": salt,
                },
            }
        )
        lib_domain_sep = signable.header
        lib_struct_hash = signable.body
        lib_digest = Web3.keccak(b"\x19\x01" + lib_domain_sep + lib_struct_hash)

        assert domain_sep == lib_domain_sep, "domain separator mismatch"
        assert struct_hash == lib_struct_hash, "struct hash mismatch"
        assert manual_digest == lib_digest, "final digest mismatch"

        # Also verify signature round-trip
        sig_hex = sign_create_escrow(ADMIN_PK, CHAIN_ID, FACTORY_ADDR, config, salt)
        sig_bytes = bytes.fromhex(sig_hex.removeprefix("0x"))
        recovered = Account.recover_message(signable, signature=sig_bytes)
        assert recovered == ADMIN_ADDR


# ══════════════════════════════════════════════════════════
# build_create_and_deposit_calldata
# ══════════════════════════════════════════════════════════

class TestBuildCalldata:
    def test_create_and_deposit_starts_with_selector(self):
        config = _make_config()
        salt = generate_salt()
        admin_sig = "0x" + "ab" * 65
        calldata = build_create_and_deposit_calldata(config, salt, admin_sig)
        # Should start with 0x and be a hex string
        assert calldata.startswith("0x")
        # Function selector is 4 bytes = 8 hex chars
        assert len(calldata) > 10

    def test_create_and_deposit_includes_admin_sig(self):
        config = _make_config()
        salt = generate_salt()
        admin_sig = sign_create_escrow(ADMIN_PK, CHAIN_ID, FACTORY_ADDR, config, salt)
        calldata = build_create_and_deposit_calldata(config, salt, admin_sig)
        assert calldata.startswith("0x")
        assert len(calldata) > 10

    def test_approve_calldata_has_correct_selector(self):
        calldata = build_approve_calldata(FACTORY_ADDR, 100_000_000)
        assert calldata.startswith("0x")
        # approve(address,uint256) selector = 0x095ea7b3
        expected_selector = Web3.keccak(text="approve(address,uint256)")[:4].hex()
        assert calldata[2:10] == expected_selector

    def test_approve_calldata_encodes_spender_and_amount(self):
        calldata = build_approve_calldata(FACTORY_ADDR, 100_000_000)
        # After 4-byte selector: 32 bytes address + 32 bytes amount = 64 bytes = 128 hex chars
        data_hex = calldata[10:]  # skip 0x + 8 char selector
        assert len(data_hex) == 128
        # Last 32 bytes should encode the amount
        amount_hex = data_hex[64:]
        assert int(amount_hex, 16) == 100_000_000

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
        assert len(t) == 9
        assert t[0] == config.token
        assert t[3] == 100_000_000
        assert isinstance(t[7], list)  # participants as list for ABI
        assert t[8] == b"\x00" * 32  # pcr0_hash

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


# ══════════════════════════════════════════════════════════
# PCR-0 support
# ══════════════════════════════════════════════════════════

FAKE_PCR0 = bytes(range(48))  # 48-byte fake PCR-0


class TestSignSettlementWithPcr0:
    def test_with_pcr0_produces_valid_signature(self):
        payouts = [(ALICE, 150_000_000), (BOB, 50_000_000)]
        sig_hex = sign_settlement(ADMIN_PK, CHAIN_ID, ESCROW_ADDR, payouts, pcr0=FAKE_PCR0)

        sig_bytes = bytes.fromhex(sig_hex.removeprefix("0x"))
        assert len(sig_bytes) == 65

    def test_with_pcr0_recovers_to_admin(self):
        payouts = [(ALICE, 150_000_000), (BOB, 50_000_000)]
        sig_hex = sign_settlement(ADMIN_PK, CHAIN_ID, ESCROW_ADDR, payouts, pcr0=FAKE_PCR0)

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
                    {"name": "pcr0", "type": "bytes"},
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
                "pcr0": FAKE_PCR0,
            },
        }

        signable = encode_typed_data(full_message=structured_data)
        sig_bytes = bytes.fromhex(sig_hex.removeprefix("0x"))
        recovered = Account.recover_message(signable, signature=sig_bytes)
        assert recovered == ADMIN_ADDR

    def test_without_pcr0_backwards_compat(self):
        """sign_settlement without pcr0 kwarg defaults to empty bytes."""
        payouts = [(ALICE, 150_000_000), (BOB, 50_000_000)]
        sig_hex = sign_settlement(ADMIN_PK, CHAIN_ID, ESCROW_ADDR, payouts)
        sig_bytes = bytes.fromhex(sig_hex.removeprefix("0x"))
        assert len(sig_bytes) == 65

    def test_different_pcr0_different_signatures(self):
        payouts = [(ALICE, 150_000_000), (BOB, 50_000_000)]
        sig1 = sign_settlement(ADMIN_PK, CHAIN_ID, ESCROW_ADDR, payouts, pcr0=FAKE_PCR0)
        sig2 = sign_settlement(ADMIN_PK, CHAIN_ID, ESCROW_ADDR, payouts, pcr0=b"\xff" * 48)
        assert sig1 != sig2


class TestEscrowConfigPcr0:
    def test_config_stores_pcr0_hash(self):
        pcr0_hash = Web3.keccak(FAKE_PCR0)
        config = _make_config(pcr0_hash=pcr0_hash)
        assert config.pcr0_hash == pcr0_hash

    def test_config_tuple_includes_pcr0_hash(self):
        pcr0_hash = Web3.keccak(FAKE_PCR0)
        config = _make_config(pcr0_hash=pcr0_hash)
        t = config.as_tuple()
        assert len(t) == 9
        assert t[8] == pcr0_hash

    def test_config_default_pcr0_hash_is_zero(self):
        config = _make_config()
        assert config.pcr0_hash == b"\x00" * 32


class TestGetEnvConfig:
    def test_settlement_timeout_default_is_24h(self):
        cfg = get_env_config()
        assert cfg["settlement_timeout"] == 86400
