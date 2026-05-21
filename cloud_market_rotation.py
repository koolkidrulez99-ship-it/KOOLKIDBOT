from __future__ import annotations

from typing import Iterable


DEFAULT_CLOUD_MARKETS = [
    "R_10",
    "R_25",
    "R_50",
    "R_75",
    "R_100",
    "1HZ10V",
    "1HZ25V",
    "1HZ50V",
    "1HZ75V",
    "1HZ100V",
    "JD10",
    "JD25",
    "JD50",
    "JD75",
    "JD100",
]


def normalize_cloud_symbol(value) -> str:
    symbol = str(value or "").strip().upper()
    return symbol


def normalize_allowed_markets(value) -> list[str]:
    if isinstance(value, str):
        raw = value.replace("\n", ",").replace(";", ",").split(",")
    elif isinstance(value, Iterable):
        raw = list(value)
    else:
        raw = []
    seen = set()
    out = []
    for item in raw:
        symbol = normalize_cloud_symbol(item)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
    return out or list(DEFAULT_CLOUD_MARKETS)


def next_market(allowed_markets, current_market) -> str:
    markets = normalize_allowed_markets(allowed_markets)
    current = normalize_cloud_symbol(current_market)
    if current not in markets:
        return markets[0]
    idx = markets.index(current)
    return markets[(idx + 1) % len(markets)]
