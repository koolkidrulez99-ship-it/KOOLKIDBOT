import threading
import time

from mt5_multi_account import app as api
from mt5_multi_account.models import ManualTradeRequest


def test_manual_multi_account_orders_are_dispatched_concurrently(monkeypatch):
    starts = []
    lock = threading.Lock()

    def fake_call(account_id, operation, payload=None, timeout=15):
        assert operation == "open_trade"
        with lock:
            starts.append((account_id, time.perf_counter()))
        time.sleep(0.08)
        return {"ticket": len(starts), "retcode": 10009, "timing": {}}

    monkeypatch.setattr(api.POOL, "call", fake_call)
    monkeypatch.setattr(api.COPY, "status", "stopped")
    result = api.manual_trade(ManualTradeRequest(
        target_account_ids=["master", "slave-1", "slave-2"],
        symbol="EURUSD", side="buy", volume=0.01,
    ))

    assert all(row["ok"] for row in result["results"].values())
    assert len(starts) == 3
    assert max(started for _, started in starts) - min(started for _, started in starts) < 0.04
