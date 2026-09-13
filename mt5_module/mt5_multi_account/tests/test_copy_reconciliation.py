from mt5_multi_account.copy_engine import CopyEngine


class FakeState:
    def __init__(self):
        self.value = {"copy_map": {}}

    def load(self):
        return dict(self.value)

    def save(self, value):
        self.value = value


class SlowSuccessPool:
    def __init__(self):
        self.items = {"slave": type("Runtime", (), {"config": {"symbol_aliases": {}}})()}
        self.calls = []

    def call(self, account_id, operation, payload=None, timeout=15):
        self.calls.append((account_id, operation, timeout))
        if operation == "account_info":
            return {"equity": 1000}
        if operation == "open_trade":
            raise TimeoutError("slow broker response")
        if operation == "positions":
            return [{"ticket": 321, "comment": "KKCOPY:123"}]
        raise AssertionError(operation)


def test_copy_open_reconciles_a_late_success_without_duplicate_buy():
    pool = SlowSuccessPool()
    engine = CopyEngine(pool, FakeState())
    engine.config = {"lot_mode": "same"}

    result = engine._copy_to_slave(
        "123",
        {"symbol": "Volatility 100 (1s) Index", "volume": 1, "type": 0, "sl": 0, "tp": 0},
        {"equity": 1000},
        "slave",
    )

    assert result == {"ok": True, "ticket": 321}
    assert [call[1] for call in pool.calls].count("open_trade") == 1
    assert engine.copy_map["123"]["slave"]["ticket"] == 321
