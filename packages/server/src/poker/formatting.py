"""Shared display formatting utilities."""

from __future__ import annotations


def format_buy_in(buy_in: int, token_decimals: int, token_symbol: str | None, mode: str) -> str:
    """Format buy-in amount for display (e.g., '1000 MONTE' or '500 credits')."""
    if buy_in == 0:
        return "Free"
    if token_decimals > 0:
        raw = buy_in / (10 ** token_decimals)
        amount = f"{raw:g}"
    else:
        amount = str(buy_in)
    symbol = token_symbol or ("credits" if mode == "offchain" else None)
    if symbol:
        return f"{amount} {symbol}"
    return amount
