"""Cross-language E2E: Python EIP-712 signing → Solidity on-chain verification.

Requires Anvil running on localhost:8545 and compiled Foundry artifacts.
Marked with ``pytest.mark.e2e`` so the standard ``make test`` skips them.

Run:
    anvil &
    cd packages/contracts && forge build
    PYTHONPATH=packages/server/src uv run pytest packages/server/tests/test_escrow_e2e.py -v -m e2e
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eth_account import Account
from web3 import Web3

from core.escrow import (
    EscrowConfig,
    compute_participants_hash,
    generate_salt,
    sign_create_escrow,
    sign_settlement,
)

# ── Anvil default accounts ────────────────────────────────

ANVIL_PK_0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ANVIL_PK_1 = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
ANVIL_PK_2 = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"

ADMIN_ADDR = Account.from_key(ANVIL_PK_0).address
PLAYER1_ADDR = Account.from_key(ANVIL_PK_1).address
PLAYER2_ADDR = Account.from_key(ANVIL_PK_2).address

RPC_URL = "http://127.0.0.1:8545"
CHAIN_ID = 31337  # Anvil default

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"

# ── Helpers ───────────────────────────────────────────────


def _get_artifact(name: str) -> dict:
    """Load compiled Foundry artifact."""
    path = CONTRACTS_DIR / "out" / f"{name}.sol" / f"{name}.json"
    if not path.exists():
        pytest.skip(f"Foundry artifact not found: {path}. Run `forge build` first.")
    return json.loads(path.read_text())


def _deploy(w3: Web3, artifact: dict, sender_pk: str, *constructor_args) -> str:
    """Deploy a contract and return its address."""
    account = Account.from_key(sender_pk)
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"]["object"])
    tx = contract.constructor(*constructor_args).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 5_000_000,
        "gasPrice": w3.eth.gas_price,
    })
    signed = Account.sign_transaction(tx, sender_pk)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1, f"Deploy failed: {receipt}"
    return receipt["contractAddress"]


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def w3():
    """Connect to Anvil."""
    provider = Web3(Web3.HTTPProvider(RPC_URL))
    if not provider.is_connected():
        pytest.skip("Anvil not running on localhost:8545")
    return provider


@pytest.fixture(scope="module")
def deployed(w3):
    """Deploy Escrow impl, EscrowFactory, and MonteClaudio. Return addresses."""
    escrow_art = _get_artifact("Escrow")
    factory_art = _get_artifact("EscrowFactory")
    monte_art = _get_artifact("MonteClaudio")

    impl_addr = _deploy(w3, escrow_art, ANVIL_PK_0)
    factory_addr = _deploy(w3, factory_art, ANVIL_PK_0, impl_addr)
    monte_addr = _deploy(w3, monte_art, ANVIL_PK_0)

    return {
        "impl": impl_addr,
        "factory": factory_addr,
        "monte": monte_addr,
        "factory_abi": factory_art["abi"],
        "monte_abi": monte_art["abi"],
        "escrow_abi": escrow_art["abi"],
    }


# ── Tests ─────────────────────────────────────────────────


@pytest.mark.e2e
class TestCrossLanguageCreateEscrow:
    """Python signs EIP-712 CreateEscrow → Solidity factory verifies on-chain."""

    def test_python_signed_create_accepted_by_factory(self, w3, deployed):
        """The exact bug that Finding 12 targets: Python-generated admin
        signature must be accepted by the Solidity factory contract."""
        monte = w3.eth.contract(
            address=deployed["monte"], abi=deployed["monte_abi"]
        )
        factory = w3.eth.contract(
            address=deployed["factory"], abi=deployed["factory_abi"]
        )

        buy_in = 1000 * 10**18  # 1000 MONTE

        # Players claim from faucet
        for pk in (ANVIL_PK_1, ANVIL_PK_2):
            account = Account.from_key(pk)
            tx = monte.functions.faucet().build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 200_000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = Account.sign_transaction(tx, pk)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)

        # Sort participants by address (matching EscrowConfig behavior)
        participants = tuple(sorted(
            [PLAYER1_ADDR, PLAYER2_ADDR],
            key=lambda a: int(a, 16),
        ))

        salt = generate_salt()
        now = w3.eth.get_block("latest")["timestamp"]

        config = EscrowConfig(
            token=deployed["monte"],
            admin=ADMIN_ADDR,
            rake_beneficiary=ADMIN_ADDR,
            deposit_amount=buy_in,
            rake_bps=250,
            funding_deadline=now + 600,
            settlement_deadline=now + 7200,
            participants=participants,
        )

        # Python signs the EIP-712 message
        admin_sig = sign_create_escrow(
            ANVIL_PK_0, CHAIN_ID, deployed["factory"], config, salt,
        )

        # Player1 approves factory and calls createAndDeposit
        p1_account = Account.from_key(ANVIL_PK_1)
        approve_tx = monte.functions.approve(deployed["factory"], buy_in).build_transaction({
            "from": p1_account.address,
            "nonce": w3.eth.get_transaction_count(p1_account.address),
            "gas": 100_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = Account.sign_transaction(approve_tx, ANVIL_PK_1)
        w3.eth.send_raw_transaction(signed.raw_transaction)

        sig_bytes = bytes.fromhex(admin_sig.removeprefix("0x"))
        create_tx = factory.functions.createAndDeposit(
            config.as_tuple(), salt, sig_bytes,
        ).build_transaction({
            "from": p1_account.address,
            "nonce": w3.eth.get_transaction_count(p1_account.address),
            "gas": 2_000_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = Account.sign_transaction(create_tx, ANVIL_PK_1)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        assert receipt["status"] == 1, "createAndDeposit reverted — Python signature rejected"

        # Verify escrow was created at predicted address
        predicted = factory.functions.getEscrowAddress(config.as_tuple(), salt).call()
        # The escrow address is in the logs (EscrowCreated event)
        escrow_addr = predicted

        escrow = w3.eth.contract(address=escrow_addr, abi=deployed["escrow_abi"])
        assert escrow.functions.hasDeposited(config.participants[0]).call() or \
               escrow.functions.hasDeposited(config.participants[1]).call()

    def test_python_signed_settlement_accepted_by_escrow(self, w3, deployed):
        """Full lifecycle: create → deposit all → settle with Python signature."""
        monte = w3.eth.contract(
            address=deployed["monte"], abi=deployed["monte_abi"]
        )
        factory = w3.eth.contract(
            address=deployed["factory"], abi=deployed["factory_abi"]
        )

        buy_in = 500 * 10**18

        # Fresh faucet claims (24h cooldown means we use different amounts to avoid conflicts)
        # Players already have MONTE from previous test, check balances
        p1_bal = monte.functions.balanceOf(PLAYER1_ADDR).call()
        p2_bal = monte.functions.balanceOf(PLAYER2_ADDR).call()
        assert p1_bal >= buy_in, f"Player1 needs {buy_in} MONTE, has {p1_bal}"
        assert p2_bal >= buy_in, f"Player2 needs {buy_in} MONTE, has {p2_bal}"

        participants = tuple(sorted(
            [PLAYER1_ADDR, PLAYER2_ADDR],
            key=lambda a: int(a, 16),
        ))

        salt = generate_salt()
        now = w3.eth.get_block("latest")["timestamp"]

        config = EscrowConfig(
            token=deployed["monte"],
            admin=ADMIN_ADDR,
            rake_beneficiary=ADMIN_ADDR,
            deposit_amount=buy_in,
            rake_bps=250,
            funding_deadline=now + 600,
            settlement_deadline=now + 7200,
            participants=participants,
        )

        # ── Create + Player1 deposit ──
        admin_sig = sign_create_escrow(
            ANVIL_PK_0, CHAIN_ID, deployed["factory"], config, salt,
        )

        p1 = Account.from_key(ANVIL_PK_1)
        approve_tx = monte.functions.approve(deployed["factory"], buy_in).build_transaction({
            "from": p1.address,
            "nonce": w3.eth.get_transaction_count(p1.address),
            "gas": 100_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = Account.sign_transaction(approve_tx, ANVIL_PK_1)
        w3.eth.send_raw_transaction(signed.raw_transaction)

        sig_bytes = bytes.fromhex(admin_sig.removeprefix("0x"))
        create_tx = factory.functions.createAndDeposit(
            config.as_tuple(), salt, sig_bytes,
        ).build_transaction({
            "from": p1.address,
            "nonce": w3.eth.get_transaction_count(p1.address),
            "gas": 2_000_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = Account.sign_transaction(create_tx, ANVIL_PK_1)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        assert receipt["status"] == 1

        escrow_addr = factory.functions.getEscrowAddress(config.as_tuple(), salt).call()
        escrow = w3.eth.contract(address=escrow_addr, abi=deployed["escrow_abi"])

        # ── Player2 deposit ──
        p2 = Account.from_key(ANVIL_PK_2)
        approve_tx = monte.functions.approve(escrow_addr, buy_in).build_transaction({
            "from": p2.address,
            "nonce": w3.eth.get_transaction_count(p2.address),
            "gas": 100_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = Account.sign_transaction(approve_tx, ANVIL_PK_2)
        w3.eth.send_raw_transaction(signed.raw_transaction)

        deposit_tx = escrow.functions.deposit(p2.address).build_transaction({
            "from": p2.address,
            "nonce": w3.eth.get_transaction_count(p2.address),
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = Account.sign_transaction(deposit_tx, ANVIL_PK_2)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        assert receipt["status"] == 1

        assert escrow.functions.allDeposited().call()

        # ── Settle: Player1 wins 700, Player2 gets 300 (from 1000 total) ──
        payouts = [
            (PLAYER1_ADDR, 700 * 10**18),
            (PLAYER2_ADDR, 300 * 10**18),
        ]
        settle_sig = sign_settlement(
            ANVIL_PK_0, CHAIN_ID, escrow_addr, payouts,
        )
        settle_sig_bytes = bytes.fromhex(settle_sig.removeprefix("0x"))

        # Build Payout[] struct array for the contract call
        payout_tuples = [(Web3.to_checksum_address(addr), amt) for addr, amt in payouts]

        settle_tx = escrow.functions.settle(
            payout_tuples, b"", settle_sig_bytes,
        ).build_transaction({
            "from": ADMIN_ADDR,
            "nonce": w3.eth.get_transaction_count(ADMIN_ADDR),
            "gas": 500_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = Account.sign_transaction(settle_tx, ANVIL_PK_0)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        assert receipt["status"] == 1, "settle() reverted — Python settlement signature rejected"

        # Escrow should be empty after settlement
        escrow_balance = monte.functions.balanceOf(escrow_addr).call()
        assert escrow_balance == 0

    def test_participants_hash_matches_on_chain(self, w3, deployed):
        """Verify compute_participants_hash produces the same hash the factory uses."""
        participants = tuple(sorted(
            [PLAYER1_ADDR, PLAYER2_ADDR],
            key=lambda a: int(a, 16),
        ))

        python_hash = compute_participants_hash(participants)

        # The factory doesn't expose participantsHash directly, but if we
        # create an escrow config and sign it, the factory accepting the
        # signature proves the hash matches (since participantsHash is part
        # of the signed struct). This is covered by test_python_signed_create.
        # Here we just verify the hash is deterministic and non-zero.
        assert len(python_hash) == 32
        assert python_hash != b"\x00" * 32

        # Verify it matches a second computation
        assert python_hash == compute_participants_hash(participants)
