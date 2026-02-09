"""Pure functions for on-chain escrow interaction.

No classes, no state. Builds calldata, computes addresses, signs settlements.
"""

from __future__ import annotations

import os
import secrets

from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

# ── Constants ─────────────────────────────────────────────

ESCROW_ABI_DEPOSIT = "deposit(address)"
ESCROW_ABI_DEPOSIT_WITH_PERMIT2 = (
    "depositWithPermit2(address,(address,uint256,uint256,uint256),address,bytes)"
)
ESCROW_ABI_RECORD_DEPOSIT = "recordDeposit(address)"
ESCROW_ABI_ALL_DEPOSITED = "allDeposited()"
ESCROW_ABI_HAS_DEPOSITED = "hasDeposited(address)"

# Canonical Permit2 address (same on all EVM chains)
PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"

# Minimal ABIs for RPC calls
ESCROW_MINIMAL_ABI = [
    {
        "inputs": [],
        "name": "allDeposited",
        "outputs": [{"type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "addr", "type": "address"}],
        "name": "hasDeposited",
        "outputs": [{"type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]

_CONFIG_COMPONENTS = [
    {"name": "token", "type": "address"},
    {"name": "admin", "type": "address"},
    {"name": "rakeBeneficiary", "type": "address"},
    {"name": "depositAmount", "type": "uint256"},
    {"name": "rakeBps", "type": "uint16"},
    {"name": "fundingDeadline", "type": "uint256"},
    {"name": "settlementDeadline", "type": "uint256"},
    {"name": "participants", "type": "address[]"},
]

_PERMIT_TRANSFER_FROM_COMPONENTS = [
    {
        "name": "permitted",
        "type": "tuple",
        "components": [
            {"name": "token", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
    },
    {"name": "nonce", "type": "uint256"},
    {"name": "deadline", "type": "uint256"},
]

FACTORY_MINIMAL_ABI = [
    {
        "inputs": [
            {"name": "config", "type": "tuple", "components": _CONFIG_COMPONENTS},
            {"name": "salt", "type": "bytes32"},
        ],
        "name": "createAndDeposit",
        "outputs": [{"name": "escrow", "type": "address"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "config", "type": "tuple", "components": _CONFIG_COMPONENTS},
            {"name": "salt", "type": "bytes32"},
            {"name": "permit", "type": "tuple", "components": _PERMIT_TRANSFER_FROM_COMPONENTS},
            {"name": "signature", "type": "bytes"},
        ],
        "name": "createAndDepositWithPermit2",
        "outputs": [{"name": "escrow", "type": "address"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "config", "type": "tuple", "components": _CONFIG_COMPONENTS},
            {"name": "salt", "type": "bytes32"},
        ],
        "name": "getEscrowAddress",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]


# ── Types ─────────────────────────────────────────────────

class EscrowConfig:
    """Value object for escrow configuration. Immutable after creation."""

    __slots__ = (
        "token", "admin", "rake_beneficiary", "deposit_amount",
        "rake_bps", "funding_deadline", "settlement_deadline", "participants",
        "_frozen",
    )

    def __init__(
        self,
        token: str,
        admin: str,
        rake_beneficiary: str,
        deposit_amount: int,
        rake_bps: int,
        funding_deadline: int,
        settlement_deadline: int,
        participants: tuple[str, ...],
    ) -> None:
        object.__setattr__(self, "token", Web3.to_checksum_address(token))
        object.__setattr__(self, "admin", Web3.to_checksum_address(admin))
        object.__setattr__(self, "rake_beneficiary", Web3.to_checksum_address(rake_beneficiary))
        object.__setattr__(self, "deposit_amount", deposit_amount)
        object.__setattr__(self, "rake_bps", rake_bps)
        object.__setattr__(self, "funding_deadline", funding_deadline)
        object.__setattr__(self, "settlement_deadline", settlement_deadline)
        # Contract requires participants sorted ascending by address
        checksummed = [Web3.to_checksum_address(p) for p in participants]
        object.__setattr__(self, "participants", tuple(sorted(checksummed, key=lambda a: int(a, 16))))
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"EscrowConfig is immutable, cannot set '{name}'")

    def as_tuple(self) -> tuple:
        """For ABI encoding."""
        return (
            self.token,
            self.admin,
            self.rake_beneficiary,
            self.deposit_amount,
            self.rake_bps,
            self.funding_deadline,
            self.settlement_deadline,
            list(self.participants),
        )


# ── Salt generation ───────────────────────────────────────

def generate_salt() -> bytes:
    """Generate a random 32-byte salt."""
    return secrets.token_bytes(32)


# ── Address computation ───────────────────────────────────

def compute_escrow_address(
    factory_address: str,
    config: EscrowConfig,
    salt: bytes,
    rpc_url: str | None = None,
) -> str:
    """Compute deterministic escrow address via factory view call.

    If rpc_url is provided, queries the factory contract on-chain.
    Otherwise, computes locally using CREATE2 formula.
    """
    factory_addr = Web3.to_checksum_address(factory_address)

    if not rpc_url:
        raise ValueError(
            "rpc_url is required to compute escrow address (local computation not supported)"
        )

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    factory = w3.eth.contract(address=factory_addr, abi=FACTORY_MINIMAL_ABI)
    return factory.functions.getEscrowAddress(config.as_tuple(), salt).call()


# ── Calldata builders ─────────────────────────────────────

def build_create_and_deposit_calldata(config: EscrowConfig, salt: bytes) -> str:
    """ABI-encoded calldata for factory.createAndDeposit(config, salt)."""
    w3 = Web3()
    factory = w3.eth.contract(abi=FACTORY_MINIMAL_ABI)
    return factory.encode_abi("createAndDeposit", [config.as_tuple(), salt])


def build_deposit_calldata(participant: str) -> str:
    """ABI-encoded calldata for escrow.deposit(participant)."""
    selector = Web3.keccak(text=ESCROW_ABI_DEPOSIT)[:4]
    encoded_addr = abi_encode(["address"], [Web3.to_checksum_address(participant)])
    return "0x" + selector.hex() + encoded_addr.hex()


# ── Chain queries ─────────────────────────────────────────

def check_all_deposited(rpc_url: str, escrow_address: str) -> bool:
    """Query escrow.allDeposited() via RPC."""
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    escrow = w3.eth.contract(
        address=Web3.to_checksum_address(escrow_address),
        abi=ESCROW_MINIMAL_ABI,
    )
    return escrow.functions.allDeposited().call()


def check_deposit_status(
    rpc_url: str,
    escrow_address: str,
    participants: tuple[str, ...],
) -> list[tuple[str, bool]]:
    """Query deposit status for each participant."""
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    escrow = w3.eth.contract(
        address=Web3.to_checksum_address(escrow_address),
        abi=ESCROW_MINIMAL_ABI,
    )
    return [
        (addr, escrow.functions.hasDeposited(Web3.to_checksum_address(addr)).call())
        for addr in participants
    ]


# ── Settlement ────────────────────────────────────────────

from poker.payout import compute_payouts as compute_payouts  # re-export


def sign_settlement(
    private_key: str,
    chain_id: int,
    escrow_address: str,
    payouts: list[tuple[str, int]],
) -> str:
    """Sign an EIP-712 settlement message.

    Returns the hex-encoded signature (r + s + v, 65 bytes).
    """
    escrow_addr = Web3.to_checksum_address(escrow_address)

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
            "chainId": chain_id,
            "verifyingContract": escrow_addr,
        },
        "message": {
            "payouts": [
                {"recipient": Web3.to_checksum_address(addr), "amount": amount}
                for addr, amount in payouts
            ],
        },
    }

    signable = encode_typed_data(full_message=structured_data)
    signed = Account.sign_message(signable, private_key=private_key)
    # Return compact signature: r (32) + s (32) + v (1) = 65 bytes
    return signed.signature.hex()


# ── Config helpers ────────────────────────────────────────

def get_server_address() -> str:
    """Derive server EOA address from SERVER_PRIVATE_KEY env var."""
    pk = os.environ.get("SERVER_PRIVATE_KEY", "")
    if not pk:
        return ""
    return Account.from_key(pk).address


def get_env_config() -> dict:
    """Read escrow-related env vars with defaults."""
    return {
        "server_private_key": os.environ.get("SERVER_PRIVATE_KEY", ""),
        "base_rpc_url": os.environ.get("BASE_RPC_URL", "http://localhost:8545"),
        "rake_bps": int(os.environ.get("RAKE_BPS", "250")),
        "rake_beneficiary": os.environ.get("RAKE_BENEFICIARY", ""),
        "factory_address": os.environ.get("FACTORY_ADDRESS", ""),
        "funding_timeout": int(os.environ.get("FUNDING_TIMEOUT", "300")),
        "settlement_timeout": int(os.environ.get("SETTLEMENT_TIMEOUT", "7200")),
        "chain_id": int(os.environ.get("CHAIN_ID", "8453")),
    }
