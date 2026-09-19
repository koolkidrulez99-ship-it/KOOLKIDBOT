from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mt5_module"))
sys.path.insert(0, str(ROOT / "mt5_module" / "mt5_bridge"))

import native_runtime  # noqa: E402
from native_strategies.common import Series  # noqa: E402


def _series(step: int = 300) -> Series:
    return Series.from_rows([
        {"time": index * step, "open": 100 + index * .01, "high": 101 + index * .01,
         "low": 99 + index * .01, "close": 100.5 + index * .01, "volume": 100}
        for index in range(40)
    ])


class FakeSignal:
    def to_dict(self):
        return {
            "valid": False,
            "stage": "SCANNING",
            "score": 0.0,
            "signal_key": None,
        }


def test_native_bot_cycle_is_locked_to_saved_symbol(monkeypatch):
    bot = {
        "id": 1009,
        "native_key": "dear_bruce",
        "symbol": "SHOULD_NOT_BE_USED",
        "settings": {"risk_percent": 0.5},
        "native_config": {
            "enabled": True,
            "account_login": 123,
            "symbol": "FXVol40",
            "allow_live": False,
        },
    }

    fetched = []
    monkeypatch.setattr(native_runtime, "_bot", lambda _bot_id: bot)
    monkeypatch.setattr(native_runtime, "_verify_account", lambda *_args, **_kwargs: ({}, {"equity": 1000}))
    monkeypatch.setattr(native_runtime, "_fetch_market", lambda login, symbol, extra_timeframes=None: (
        fetched.append((login, symbol, set(extra_timeframes or [])))
        or {"M5": _series(300), "H4": _series(14400), "symbol_info": {}}, {}
    ))
    monkeypatch.setattr(native_runtime, "evaluate", lambda *_args, **_kwargs: FakeSignal())
    monkeypatch.setattr(native_runtime, "_positions", lambda _login: [])
    monkeypatch.setattr(native_runtime, "_manage_open_position", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(native_runtime, "_patch_bot", lambda *_args, **_kwargs: None)

    native_runtime._cycle(1009)
    assert fetched == [(123, "FXVol40", {"M5", "H4"})]


def test_native_position_size_respects_user_risk_cap(monkeypatch):
    bot = {"account_login": 123, "settings": {"risk_percent": 0.5}}
    signal = {"entry": 100.0, "sl": 99.0, "risk_percent": 1.0}
    account = {"equity": 1000.0}
    info = {
        "trade_tick_size": 1.0,
        "trade_tick_value_loss": 1.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
    }

    monkeypatch.setattr(native_runtime, "_effective_equity", lambda *_args: 1000.0)
    monkeypatch.setattr(native_runtime, "read_state", lambda: {"risk": []})
    volume = native_runtime._risk_volume(signal, account, info, bot)

    # 0.5% of $1,000 = $5 risk; $1 risk per lot at this synthetic price geometry.
    assert volume == 5.0


def test_market_fetch_only_adds_user_selected_extra_timeframes(monkeypatch):
    paths = []

    def account_request(login, path, timeout=15):
        paths.append(path)
        if path.startswith("/quotes"):
            return [{"bid": 100.0, "ask": 100.1}]
        if path.startswith("/symbol-info"):
            return {"point": 0.01}
        if path.startswith("/candles/"):
            return [
                {"time": 1, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 100}
            ]
        raise AssertionError(path)

    monkeypatch.setattr(native_runtime.multi_account_client, "account_request", account_request)
    market, _ = native_runtime._fetch_market(123, "FXV40", {"M30"})

    candle_paths = [path for path in paths if path.startswith("/candles/")]
    assert any("timeframe=M5" in path for path in candle_paths)
    assert any("timeframe=M15" in path for path in candle_paths)
    assert any("timeframe=H1" in path for path in candle_paths)
    assert any("timeframe=H4" in path for path in candle_paths)
    assert any("timeframe=D1&count=10" in path for path in candle_paths)
    assert any("timeframe=M30" in path for path in candle_paths)
    assert not any("timeframe=M1&" in path for path in candle_paths)
    assert "M30" in market
