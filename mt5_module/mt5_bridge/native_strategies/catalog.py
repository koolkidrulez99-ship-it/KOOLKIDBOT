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
    1008: {
        "key": "human_apostle", "name": "HUMAN APOSTLE", "title": "H4 / M15 Structure Reversal",
        "subtitle": "H4 bias · M15 trendline break · MSS · retest",
        "description": "Market-structure reversal preset built from the Human Apostle MQ5. It tracks H4 bias and M15 structure, waits for an opposing trendline break, protected-structure shift, later retest and rejection, then enters with source-derived 1% risk and a 2R target.",
        "source": "HumanApostle_EA.mq5", "source_sha256": "7cf6d31c3b6e168a87dc6d4fe6272b2d46a254b223bbed24ad6c1be0ed3f6242",
        "version": "1.00", "magic": 4152026, "ready": True, "entry_tf": "M15", "bias_tf": "H4", "risk_percent": 1.0,
    },
    1009: {
        "key": "dear_bruce", "name": "DEAR BRUCE", "title": "Enhanced Market Structure",
        "subtitle": "H4 alignment · M5 break / shift / retest · RR management",
        "description": "Enhanced market-structure preset built from Dear Bruce Premium v2.20. It follows the break → protected-structure shift → later retest sequence on M5 with H4 alignment, source-derived 1% risk, 2R targets, break-even at 1R and RR trailing from 1.5R.",
        "source": "DEAR_BRUCE_PREMIUM.mq5", "source_sha256": "4e4aed61836b560f9b2f12f86ac373efedeb8572d71715bd5d42bcae400956f4",
        "version": "2.20", "magic": 22082605, "ready": True, "entry_tf": "M5", "bias_tf": "H4", "risk_percent": 1.0,
        "max_trades_per_day": 3, "max_daily_loss_percent": 2.0,
    },
}
