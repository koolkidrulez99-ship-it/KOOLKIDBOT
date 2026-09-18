from __future__ import annotations

from typing import Any

NATIVE_PRESETS: dict[int, dict[str, Any]] = {
    1000: {"key": "primordial_black", "name": "PRIMORDIAL BLACK", "title": "Liquidity Confluence Sniper", "subtitle": "Sweep · Displacement · FVG / Order Block", "source": "Primordial_Black.mq5", "magic": 26033177, "ready": True, "entry_tf": "M5", "bias_tf": "H4 + H1"},
    1001: {"key": "primordial_blue", "name": "PRIMORDIAL BLUE", "title": "Trendline Break & Retest", "subtitle": "Liquidity confluence · Trendline break · Retest", "source": "Primordial_Blue.mq5", "magic": 26033177, "ready": True, "entry_tf": "M5", "bias_tf": "H4 + H1"},
    1002: {"key": "primordial_emerald", "name": "PRIMORDIAL EMERALD", "title": "Fibonacci Precision", "subtitle": "Liquidity raid · Fib sweet spot · Price action", "source": "Primordial_Emerald.mq5", "magic": 26033178, "ready": True, "entry_tf": "M5", "bias_tf": "H4 + H1"},
    1003: {"key": "primordial_gold", "name": "PRIMORDIAL GOLD", "title": "Compression Sweep Expansion", "subtitle": "Compression · Sweep · Reclaim · BOS", "source": "Primordial_Gold.mq5", "magic": 26040101, "ready": True, "entry_tf": "M5", "bias_tf": "H4 + H1"},
    1004: {"key": "primordial_purple", "name": "PRIMORDIAL PURPLE", "title": "Orderflow MSS Sniper", "subtitle": "Order Block · FVG · Displacement · MSS", "source": "Primordial_Purple.mq5", "magic": 26040217, "ready": True, "entry_tf": "M5", "bias_tf": "H4 + H1"},
    1005: {"key": "primordial_red", "name": "PRIMORDIAL RED", "title": "Liquidity Raid Retracement", "subtitle": "Sweep · Fibonacci pullback · Momentum", "source": "Primordial_Red.mq5", "magic": 26033178, "ready": True, "entry_tf": "M5", "bias_tf": "H4 + H1"},
    1006: {"key": "primordial_silver", "name": "PRIMORDIAL SILVER", "title": "Range Sweep Reversal", "subtitle": "H1 range · M15 break zone · M5 MSS", "source": "Primordial_Silver.mq5", "magic": 90412026, "ready": True, "entry_tf": "M5", "bias_tf": "H1"},
    1007: {"key": "primordial_white", "name": "PRIMORDIAL WHITE", "title": "Opening Range Specialist", "subtitle": "First 4H range · Sweep / breakout retest", "source": "Primordial_White.mq5", "magic": 26033179, "ready": True, "entry_tf": "M5", "bias_tf": "H4 + H1"},
    1008: {"key": "black_rock", "name": "BLACK ROCK", "title": "Native Source Required", "subtitle": "MQ5 source is required for a faithful native port", "source": None, "magic": 511008, "ready": False, "entry_tf": None, "bias_tf": None},
    1009: {"key": "dear_bruce_premium", "name": "DEAR BRUCE PREMIUM", "title": "Native Source Required", "subtitle": "MQ5 source is required for a faithful native port", "source": None, "magic": 511009, "ready": False, "entry_tf": None, "bias_tf": None},
}
