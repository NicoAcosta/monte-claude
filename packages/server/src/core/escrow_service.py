"""On-chain escrow operations — config, funding, settlement."""

from __future__ import annotations

import logging
import time as _time
from typing import Any

_log = logging.getLogger("poker.escrow")

from core.attestation import NsmError, get_attestation
from core.escrow import (
    EscrowConfig,
    build_approve_calldata,
    build_create_and_deposit_calldata,
    build_deposit_calldata,
    check_deposit_status,
    compute_escrow_address,
    generate_salt,
    get_env_config,
    get_server_address,
    sign_create_escrow,
    sign_settlement,
)
from core.audit import EscrowAuditStore
from core.game_protocol import GameProtocol
from core.game_config import GameConfig
from core.payout import compute_payouts
from web3 import Web3


def _build_escrow_guide(
    *,
    token: str,
    factory_address: str,
    escrow_address: str,
    calldata_approve_factory: str,
    calldata_approve_escrow: str,
    calldata_create_and_deposit: str,
    calldata_deposit_example: str,
    game_id: str,
) -> dict[str, Any]:
    """Build step-by-step deposit guide as structured transactions.

    Each step is a {to, data, description} — agents can do:
      cast send <to> <data> --rpc-url $RPC_URL --private-key $KEY
    Zero ABI encoding required.
    """
    return {
        "first_depositor": {
            "steps": [
                {"to": token, "data": calldata_approve_factory, "description": "Approve factory to spend your tokens"},
                {"to": factory_address, "data": calldata_create_and_deposit, "description": "Deploy escrow and deposit"},
            ],
        },
        "subsequent_depositor": {
            "steps": [
                {"to": token, "data": calldata_approve_escrow, "description": "Approve escrow to spend your tokens"},
                {"to": escrow_address, "data": calldata_deposit_example, "description": "Deposit tokens into escrow (replace with your calldata_deposit)"},
            ],
        },
        "verification": f"GET /api/games/{game_id}/funding",
        "notes": [
            "Each step is: cast send <to> <data> --rpc-url $RPC_URL --private-key $PRIVATE_KEY",
            "The first depositor deploys the escrow via createAndDeposit on the factory.",
            "Subsequent depositors MUST wait until the escrow is deployed before depositing.",
            "Use your own address's calldata_deposit value from the response (not the example above).",
        ],
    }


def get_escrow_info(
    game: GameProtocol,
    config: GameConfig,
    *,
    audit: EscrowAuditStore | None = None,
    game_id: str = "",
) -> dict[str, Any]:
    """Generate or return cached escrow config for a full on-chain game.

    Raises ValueError for validation errors, RuntimeError for server config issues.
    Returns a dict with all fields needed for the EscrowInfoResponse.
    """
    if config.buy_in <= 0:
        raise ValueError("Not a funded game")
    if not config.is_at_capacity(game.player_count):
        raise ValueError("Game is not full yet")

    env = get_env_config()
    server_addr = get_server_address()
    if not server_addr:
        raise RuntimeError("Server private key not configured")
    if not env["factory_address"]:
        raise RuntimeError("Factory address not configured")

    if config.escrow_config is None:
        if config.escrow_salt is None:
            config.escrow_salt = generate_salt()

        wallets = tuple(
            p.wallet_address for p in game.players
            if p.wallet_address is not None
        )

        # Fetch PCR-0 from NSM (enclave) for on-chain binding
        try:
            attest_result = get_attestation()
            pcr0 = attest_result.payload.pcrs.get(0, b"")
            pcr0_hash = bytes(Web3.keccak(pcr0)) if pcr0 else b"\x00" * 32
        except NsmError:
            pcr0_hash = b"\x00" * 32  # dev mode — no enforcement

        now = int(_time.time())
        cfg = EscrowConfig(
            token=config.token or "",
            admin=server_addr,
            rake_beneficiary=env["rake_beneficiary"] or server_addr,
            deposit_amount=config.buy_in,
            rake_bps=env["rake_bps"],
            funding_deadline=now + env["funding_timeout"],
            settlement_deadline=now + env["funding_timeout"] + env["settlement_timeout"],
            participants=wallets,
            pcr0_hash=pcr0_hash,
        )
        config.escrow_config = cfg
        config.pcr0_hash = pcr0_hash
        config.escrow_address = compute_escrow_address(
            env["factory_address"], cfg, config.escrow_salt, rpc_url=env["base_rpc_url"],
        )

    cfg = config.escrow_config
    _log.info("escrow_config address=%s", config.escrow_address)
    if audit and game_id:
        audit.record(game_id, "config_created", escrow_address=config.escrow_address)

    admin_signature = sign_create_escrow(
        env["server_private_key"], env["chain_id"],
        env["factory_address"], cfg, config.escrow_salt,
    )
    config.admin_signature = admin_signature

    calldata_create = build_create_and_deposit_calldata(cfg, config.escrow_salt, admin_signature)
    calldata_deposits = {
        addr: build_deposit_calldata(addr)
        for addr in cfg.participants
    }
    calldata_approve_factory = build_approve_calldata(env["factory_address"], cfg.deposit_amount)
    calldata_approve_escrow = build_approve_calldata(config.escrow_address or "", cfg.deposit_amount)

    # Pick first participant's deposit calldata as example for the guide
    first_deposit_example = next(iter(calldata_deposits.values()), "")

    guide = _build_escrow_guide(
        token=cfg.token,
        factory_address=env["factory_address"],
        escrow_address=config.escrow_address or "",
        calldata_approve_factory=calldata_approve_factory,
        calldata_approve_escrow=calldata_approve_escrow,
        calldata_create_and_deposit=calldata_create,
        calldata_deposit_example=first_deposit_example,
        game_id=game_id,
    )

    return {
        "escrow_address": config.escrow_address,
        "factory_address": env["factory_address"],
        "salt": "0x" + config.escrow_salt.hex(),
        "config": cfg,
        "admin_signature": admin_signature,
        "calldata_create_and_deposit": calldata_create,
        "calldata_deposit": calldata_deposits,
        "calldata_approve_factory": calldata_approve_factory,
        "calldata_approve_escrow": calldata_approve_escrow,
        "funding_deadline": cfg.funding_deadline,
        "settlement_deadline": cfg.settlement_deadline,
        "guide": guide,
    }


def check_funding(
    game: GameProtocol,
    config: GameConfig,
    *,
    audit: EscrowAuditStore | None = None,
    game_id: str = "",
) -> dict[str, Any]:
    """Check deposit status for all participants.

    Raises ValueError for validation errors.
    Returns dict with all_deposited + deposits list.
    """
    if config.buy_in <= 0:
        raise ValueError("Not a funded game")
    if config.escrow_address is None:
        raise ValueError("Escrow not yet configured (call /escrow first)")

    env = get_env_config()
    wallets = tuple(
        p.wallet_address for p in game.players
        if p.wallet_address is not None
    )

    try:
        statuses = check_deposit_status(env["base_rpc_url"], config.escrow_address, wallets)
    except Exception:
        raise ValueError(
            f"Cannot check deposits — the escrow contract at {config.escrow_address} "
            "may not be deployed yet. The first depositor must call createAndDeposit "
            "on the factory to deploy it."
        )
    all_deposited = all(deposited for _, deposited in statuses)

    _log.info("funding_check all_deposited=%s count=%d", all_deposited, len(statuses))
    if audit and game_id:
        audit.record(game_id, "funding_checked", escrow_address=config.escrow_address,
                     details=f"all_deposited={all_deposited}")
    if all_deposited:
        config.funded = True

    wallet_to_name: dict[str, str] = {}
    for p in game.players:
        if p.wallet_address:
            wallet_to_name[p.wallet_address.lower()] = p.name

    return {
        "all_deposited": all_deposited,
        "statuses": statuses,
        "wallet_to_name": wallet_to_name,
    }


def get_settlement(
    game: GameProtocol,
    config: GameConfig,
    *,
    audit: EscrowAuditStore | None = None,
    game_id: str = "",
) -> dict[str, Any]:
    """Compute on-chain settlement payouts and sign them.

    Raises ValueError for validation errors, RuntimeError for server config issues.
    """
    if config.buy_in <= 0:
        raise ValueError("Not a funded game")
    if not game.game_over:
        raise ValueError("Game is not over yet")
    if config.escrow_address is None:
        raise ValueError("Escrow not configured")

    env = get_env_config()
    if not env["server_private_key"]:
        raise RuntimeError("Server private key not configured")

    player_chips: dict[str, int] = {}
    for p in game.players:
        if p.wallet_address:
            player_chips[p.wallet_address] = p.chips

    payouts = compute_payouts(player_chips, config.buy_in, game.starting_chips)

    # Fetch PCR-0 for settlement signature
    pcr0_hash = config.pcr0_hash or b"\x00" * 32
    if pcr0_hash != b"\x00" * 32:
        try:
            attest_result = get_attestation()
            pcr0 = attest_result.payload.pcrs.get(0, b"")
        except NsmError:
            raise RuntimeError("Attestation required for settlement but NSM unavailable")
    else:
        pcr0 = b""

    sig = sign_settlement(
        env["server_private_key"],
        env["chain_id"],
        config.escrow_address,
        payouts,
        pcr0=pcr0,
    )

    _log.info("settlement_signed address=%s payout_count=%d", config.escrow_address, len(payouts))
    if audit and game_id:
        audit.record(game_id, "settlement_signed", escrow_address=config.escrow_address)
    return {
        "payouts": payouts,
        "signature": sig,
        "escrow_address": config.escrow_address,
        "pcr0": pcr0,
    }
