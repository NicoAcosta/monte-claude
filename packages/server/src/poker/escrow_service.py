"""On-chain escrow operations — config, funding, settlement."""

from __future__ import annotations

import time as _time
from typing import Any

from poker.escrow import (
    EscrowConfig,
    build_create_and_deposit_calldata,
    build_deposit_calldata,
    check_deposit_status,
    compute_escrow_address,
    generate_salt,
    get_env_config,
    get_server_address,
    sign_settlement,
)
from poker.game import Game, STARTING_CHIPS
from poker.payout import compute_payouts


def get_escrow_info(game: Game) -> dict[str, Any]:
    """Generate or return cached escrow config for a full on-chain game.

    Raises ValueError for validation errors, RuntimeError for server config issues.
    Returns a dict with all fields needed for the EscrowInfoResponse.
    """
    if game.buy_in <= 0:
        raise ValueError("Not a funded game")
    if not game.is_full:
        raise ValueError("Game is not full yet")

    env = get_env_config()
    server_addr = get_server_address()
    if not server_addr:
        raise RuntimeError("Server private key not configured")
    if not env["factory_address"]:
        raise RuntimeError("Factory address not configured")

    if game.escrow_config is None:
        if game.escrow_salt is None:
            game.escrow_salt = generate_salt()

        wallets = tuple(
            p.wallet_address for p in game._players
            if p.wallet_address is not None
        )

        now = int(_time.time())
        cfg = EscrowConfig(
            token=game.token or "",
            admin=server_addr,
            rake_beneficiary=env["rake_beneficiary"] or server_addr,
            deposit_amount=game.buy_in,
            rake_bps=env["rake_bps"],
            funding_deadline=now + env["funding_timeout"],
            settlement_deadline=now + env["funding_timeout"] + env["settlement_timeout"],
            participants=wallets,
        )
        game.escrow_config = cfg
        game.escrow_address = compute_escrow_address(
            env["factory_address"], cfg, game.escrow_salt, rpc_url=env["base_rpc_url"],
        )

    cfg = game.escrow_config

    calldata_create = build_create_and_deposit_calldata(cfg, game.escrow_salt)
    calldata_deposits = {
        addr: build_deposit_calldata(addr)
        for addr in cfg.participants
    }

    return {
        "escrow_address": game.escrow_address,
        "factory_address": env["factory_address"],
        "salt": "0x" + game.escrow_salt.hex(),
        "config": cfg,
        "calldata_create_and_deposit": calldata_create,
        "calldata_deposit": calldata_deposits,
        "funding_deadline": cfg.funding_deadline,
        "settlement_deadline": cfg.settlement_deadline,
    }


def check_funding(game: Game) -> dict[str, Any]:
    """Check deposit status for all participants.

    Raises ValueError for validation errors.
    Returns dict with all_deposited + deposits list.
    """
    if game.buy_in <= 0:
        raise ValueError("Not a funded game")
    if game.escrow_address is None:
        raise ValueError("Escrow not yet configured (call /escrow first)")

    env = get_env_config()
    wallets = tuple(
        p.wallet_address for p in game._players
        if p.wallet_address is not None
    )

    statuses = check_deposit_status(env["base_rpc_url"], game.escrow_address, wallets)
    all_deposited = all(deposited for _, deposited in statuses)

    if all_deposited:
        game.funded = True

    wallet_to_name: dict[str, str] = {}
    for p in game._players:
        if p.wallet_address:
            wallet_to_name[p.wallet_address.lower()] = p.name

    return {
        "all_deposited": all_deposited,
        "statuses": statuses,
        "wallet_to_name": wallet_to_name,
    }


def get_settlement(game: Game) -> dict[str, Any]:
    """Compute on-chain settlement payouts and sign them.

    Raises ValueError for validation errors, RuntimeError for server config issues.
    """
    if game.buy_in <= 0:
        raise ValueError("Not a funded game")
    if not game.game_over:
        raise ValueError("Game is not over yet")
    if game.escrow_address is None:
        raise ValueError("Escrow not configured")

    env = get_env_config()
    if not env["server_private_key"]:
        raise RuntimeError("Server private key not configured")

    player_chips: dict[str, int] = {}
    for p in game._players:
        if p.wallet_address:
            player_chips[p.wallet_address] = p.chips

    payouts = compute_payouts(player_chips, game.buy_in, STARTING_CHIPS)

    sig = sign_settlement(
        env["server_private_key"],
        env["chain_id"],
        game.escrow_address,
        payouts,
    )

    return {
        "payouts": payouts,
        "signature": sig,
        "escrow_address": game.escrow_address,
    }
