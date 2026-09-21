import tempfile
from pathlib import Path

from .copy_engine import COPY_MAGIC, CopyEngine
from .state import State


class Runtime:
    config = {"symbol_aliases": {}}


class Pool:
    def __init__(self):
        self.items = {"slave": Runtime()}
        self.rows = {
            "slave": [
                {"ticket": 11, "magic": COPY_MAGIC, "comment": "KKCOPY:100"},
                {"ticket": 12, "magic": COPY_MAGIC, "comment": "KKC2:200"},
            ]
        }

    def call(self, account_id, op, payload=None, timeout=15):
        if op == "positions":
            return list(self.rows.get(account_id, []))
        if op == "account_info":
            return {"balance": 1000.0, "equity": 1000.0, "margin": 0.0}
        raise AssertionError((account_id, op, payload))


def test_copy_group_state_is_isolated_and_group1_keeps_legacy_keys():
    tmp = tempfile.TemporaryDirectory()
    try:
        state = State(Path(tmp.name) / "state.json")
        state.save({"accounts": {}, "copy_map": {"100": {"slave": {"ticket": 11}}}})
        pool = Pool()
        group1 = CopyEngine(pool, state, "1")
        group2 = CopyEngine(pool, state, "2")

        group1.copy_map = {"100": {"slave": {"ticket": 11}}}
        group2.copy_map = {"200": {"slave": {"ticket": 12}}}
        group1.persist_map()
        group2.persist_map()

        saved = state.load()
        assert saved["copy_map"] == group1.copy_map
        assert saved["copy_map_2"] == group2.copy_map
        assert CopyEngine(pool, state, "1").copy_map == group1.copy_map
        assert CopyEngine(pool, state, "2").copy_map == group2.copy_map
    finally:
        tmp.cleanup()


def test_shared_slave_trade_limit_counts_only_its_master_group():
    tmp = tempfile.TemporaryDirectory()
    try:
        state = State(Path(tmp.name) / "state.json")
        state.save({"accounts": {}})
        pool = Pool()
        group1 = CopyEngine(pool, state, "1")
        group2 = CopyEngine(pool, state, "2")
        group1.config = {"limit_copied_trades": True, "max_copied_trades_per_slave": 1}
        group2.config = {"limit_copied_trades": True, "max_copied_trades_per_slave": 1}

        assert len(group1._open_copy_positions("slave")) == 1
        assert len(group2._open_copy_positions("slave")) == 1
        assert group1._copy_slot_available("slave")[0] is False
        assert group2._copy_slot_available("slave")[0] is False
    finally:
        tmp.cleanup()


def test_copy_generated_position_is_never_re_copied_by_other_group():
    tmp = tempfile.TemporaryDirectory()
    try:
        state = State(Path(tmp.name) / "state.json")
        state.save({"accounts": {}})
        engine = CopyEngine(Pool(), state, "2")
        engine.config = {"source_filter": "all"}

        assert engine.passes_filter({"magic": 0}) is True
        assert engine.passes_filter({"magic": 12345}) is True
        assert engine.passes_filter({"magic": COPY_MAGIC}) is False
    finally:
        tmp.cleanup()
