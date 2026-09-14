from types import SimpleNamespace
from unittest import TestCase

from mt5_module.mt5_ea_worker.worker import COPY_MAGIC, _bot_trade_candidate, _resolve_bot_magic


class BotMetricsAttributionTests(TestCase):
    def item(self, *, ticket=1, magic=812345, comment="Dear Bruce", reason=3, symbol="USDCAD"):
        return SimpleNamespace(ticket=ticket, magic=magic, comment=comment, reason=reason, symbol=symbol)

    def test_only_expert_trade_for_assigned_symbol_is_candidate(self):
        row = {"symbol": "USDCAD"}
        self.assertTrue(_bot_trade_candidate(self.item(), row, set(), 3))
        self.assertFalse(_bot_trade_candidate(self.item(reason=0), row, set(), 3))
        self.assertFalse(_bot_trade_candidate(self.item(symbol="EURUSD"), row, set(), 3))
        self.assertFalse(_bot_trade_candidate(self.item(ticket=7), row, {7}, 3))

    def test_manual_and_copy_orders_are_excluded(self):
        row = {"symbol": "USDCAD"}
        self.assertFalse(_bot_trade_candidate(self.item(magic=0, comment="KKM:manual"), row, set(), 3))
        self.assertFalse(_bot_trade_candidate(self.item(magic=COPY_MAGIC, comment="KKCOPY:123"), row, set(), 3))
        self.assertFalse(_bot_trade_candidate(self.item(magic=510999, comment="KOOLKID Hub"), row, set(), 3))

    def test_unique_magic_is_bound_and_ambiguous_magic_is_rejected(self):
        row = {}
        magic, status = _resolve_bot_magic([self.item(magic=812345), self.item(ticket=2, magic=812345)], row)
        self.assertEqual((magic, status), (812345, "verified"))
        self.assertEqual(row["detected_magic"], 812345)

        magic, status = _resolve_bot_magic([self.item(magic=1), self.item(ticket=2, magic=2)], {})
        self.assertEqual((magic, status), (None, "ambiguous"))

