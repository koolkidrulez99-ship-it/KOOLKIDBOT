from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mt5_module"))
sys.path.insert(0, str(ROOT / "mt5_module" / "mt5_bridge"))

import backtest_manager  # noqa: E402


def test_backtest_clone_skips_live_history_and_tick_caches(tmp_path):
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"

    (source / "Bases" / "Broker-Demo" / "history").mkdir(parents=True)
    (source / "Bases" / "Broker-Demo" / "ticks").mkdir(parents=True)
    (source / "Bases" / "Broker-Demo" / "symbols").mkdir(parents=True)
    (source / "Tester" / "cache").mkdir(parents=True)
    (source / "Logs").mkdir(parents=True)

    (source / "terminal64.exe").write_bytes(b"terminal")
    (source / "Bases" / "Broker-Demo" / "history" / "EURUSD2026.hcc").write_bytes(b"locked-history")
    (source / "Bases" / "Broker-Demo" / "ticks" / "EURUSD2026.tks").write_bytes(b"locked-ticks")
    (source / "Bases" / "Broker-Demo" / "symbols" / "symbols.raw").write_bytes(b"broker-symbols")
    (source / "Tester" / "cache" / "stale.bin").write_bytes(b"stale-tester-cache")
    (source / "Logs" / "terminal.log").write_text("live log", encoding="utf-8")

    backtest_manager._copy_runtime(source, runtime)

    assert (runtime / "terminal64.exe").read_bytes() == b"terminal"
    assert (runtime / "Bases" / "Broker-Demo" / "symbols" / "symbols.raw").read_bytes() == b"broker-symbols"
    assert not (runtime / "Bases" / "Broker-Demo" / "history" / "EURUSD2026.hcc").exists()
    assert not (runtime / "Bases" / "Broker-Demo" / "ticks" / "EURUSD2026.tks").exists()
    assert not (runtime / "Tester").exists()
    assert not (runtime / "Logs").exists()


def test_backtest_clone_retries_windows_sharing_violation(monkeypatch, tmp_path):
    source = tmp_path / "source.bin"
    target = tmp_path / "target.bin"
    source.write_bytes(b"ok")
    calls = {"count": 0}
    real_copy2 = backtest_manager.shutil.copy2

    def flaky_copy(src, dst):
        calls["count"] += 1
        if calls["count"] < 3:
            exc = OSError("sharing violation")
            exc.winerror = 32
            raise exc
        return real_copy2(src, dst)

    monkeypatch.setattr(backtest_manager.shutil, "copy2", flaky_copy)
    monkeypatch.setattr(backtest_manager.time, "sleep", lambda *_args: None)

    result = backtest_manager._copy_runtime_file(str(source), str(target))

    assert calls["count"] == 3
    assert Path(result).read_bytes() == b"ok"


def test_backtest_log_fallback_recovers_balance_and_trade_count():
    log = """
    Core 01 2026.09.22 01:00:00 entry opened: BUY
    Core 01 Alert: entry opened: BUY
    Core 01 2026.09.22 03:45:00 entry opened: BUY
    Core 01 Alert: entry opened: BUY
    Core 01 final balance 9949.90 USD
    """
    result = backtest_manager._parse_tester_log_summary(log, 10000.0)

    assert result["final_balance"] == 9949.90
    assert result["net_profit"] == -50.10
    assert result["total_trades"] == 2


def test_public_backtest_result_derives_final_balance_when_report_omits_it():
    row = {
        "id": "bt-test",
        "status": "complete",
        "deposit": 10000,
        "result": {"net_profit": 125.55, "total_trades": 8},
    }

    public = backtest_manager._public_job(row)

    assert public["result"]["final_balance"] == 10125.55
    assert public["result"]["net_profit"] == 125.55


def test_tester_config_writes_runtime_report_name(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    job = {
        "job_dir": str(job_dir),
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "model": 4,
        "date_from": "2026-01-01",
        "date_to": "2026-02-01",
        "deposit": 10000,
        "leverage": 100,
    }
    config = backtest_manager._write_tester_config(
        job,
        runtime,
        "KOOLKIDBacktests\\Demo.ex5",
        None,
        job_dir / "report.html",
    )

    text = config.read_text(encoding="utf-16")
    assert "Report=KOOLKID_Backtest_Report.html" in text
