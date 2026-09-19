from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mt5_module"))
sys.path.insert(0, str(ROOT / "mt5_module" / "mt5_bridge"))

from native_strategies.catalog import NATIVE_PRESETS  # noqa: E402
from native_strategies.common import Series  # noqa: E402
from native_strategies.registry import ready_keys  # noqa: E402
from native_strategies.scalper_x import evaluate_scalper_x  # noqa: E402


def _bars(start: int, count: int, base: float, step: float):
    rows = []
    for i in range(count):
        opened = base + i * step
        closed = opened + step * 0.7
        rows.append({
            "time": start + i * 60, "open": opened,
            "high": max(opened, closed) + abs(step) * 0.25,
            "low": min(opened, closed) - abs(step) * 0.25,
            "close": closed, "volume": 100,
        })
    return rows


def test_scalper_x_is_registered_and_uses_completed_candles():
    assert NATIVE_PRESETS[1010]["key"] == "koolkid_scalper_x"
    assert "koolkid_scalper_x" in ready_keys()
    h1 = _bars(100000, 66, 100.0, 0.08)
    m5 = []
    for i in range(44):
        base = 100.0 + (i % 4) * 0.01
        m5.append({"time": 200000 + i * 300, "open": base, "high": base + 0.08, "low": base - 0.08, "close": base + 0.01, "volume": 100})
    m5.append({"time": 213200, "open": 100.02, "high": 100.85, "low": 99.98, "close": 100.78, "volume": 150})
    m5.append({"time": 213500, "open": 100.78, "high": 100.80, "low": 100.70, "close": 100.76, "volume": 10})
    signal = evaluate_scalper_x({
        "M5": Series.from_rows(m5), "H1": Series.from_rows(h1),
        "quote": {"bid": 100.77, "ask": 100.79, "spread_points": 2},
        "symbol_info": {"point": 0.01, "trade_stops_level": 1},
        "account_login": 123, "symbol": "FXV50",
    })
    assert signal.valid and signal.decision == "BUY" and signal.stage == "READY"
    assert signal.rules["completed_candles_only"] is True


def test_scalper_x_has_no_third_party_signal_dependency():
    source = Path(__file__).with_name("native_strategies").joinpath("scalper_x.py").read_text(encoding="utf-8").lower()
    for forbidden in ("robebank", "robebankai", "http://", "https://", "serverurl", "bridgekey"):
        assert forbidden not in source
