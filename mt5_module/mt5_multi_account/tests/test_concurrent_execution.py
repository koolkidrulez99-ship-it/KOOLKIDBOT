import threading
import time

from mt5_multi_account import app as api
from mt5_multi_account.models import ManualTradeRequest
from hub_auth import reset_workspace, set_workspace


def test_manual_multi_account_orders_are_dispatched_concurrently(monkeypatch):
    starts = []
    lock = threading.Lock()

    def fake_call(account_id, operation, payload=None, timeout=15):
        if operation == "account_info":
            return {"trade_mode": 0, "read_only": False, "access_mode": "trading"}
        assert operation == "open_trade"
        with lock:
            starts.append((account_id, time.perf_counter()))
        time.sleep(0.08)
        return {"ticket": len(starts), "retcode": 10009, "timing": {}}

    token = set_workspace("test-concurrent-execution")
    try:
        runtime = api._runtime()
        monkeypatch.setattr(runtime.pool, "call", fake_call)
        monkeypatch.setattr(runtime.copy, "status", "stopped")
        result = api.manual_trade(ManualTradeRequest(
            target_account_ids=["master", "slave-1", "slave-2"],
            symbol="EURUSD", side="buy", volume=0.01,
        ))

        assert all(row["ok"] for row in result["results"].values())
        assert len(starts) == 3
        assert max(started for _, started in starts) - min(started for _, started in starts) < 0.04
    finally:
        reset_workspace(token)
