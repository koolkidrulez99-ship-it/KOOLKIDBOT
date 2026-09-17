from __future__ import annotations

import unittest

from .engine import completed_candles, detect_swings, run_human_apostle_trial, structure_at


def candle(ts: int, o: float, h: float, l: float, c: float):
    return {"time": ts, "open": o, "high": h, "low": l, "close": c, "volume": 100}


class CandleTests(unittest.TestCase):
    def test_forming_candle_is_excluded(self):
        rows = [
            candle(0, 10, 11, 9, 10.5),
            candle(900, 10.5, 12, 10, 11.5),
            candle(1800, 11.5, 12, 11, 11.8),
        ]
        closed = completed_candles(rows, "M15", now_ts=2600)
        self.assertEqual([row["time"] for row in closed], [0, 900])

    def test_rows_are_sorted_and_deduplicated(self):
        rows = [
            candle(900, 10, 12, 9, 11),
            candle(0, 9, 10, 8, 9.5),
            candle(900, 10, 13, 9, 12),
        ]
        closed = completed_candles(rows, "M15", now_ts=4000)
        self.assertEqual(len(closed), 2)
        self.assertEqual(closed[1]["high"], 13)


class SwingTests(unittest.TestCase):
    def test_fractal_swings_are_confirmed_and_labeled(self):
        lows = [10, 9, 7, 9, 10, 9, 8, 10, 11, 10, 9]
        highs = [11, 12, 13, 12, 11, 13, 14, 13, 12, 15, 14]
        rows = [candle(i * 900, (h + l) / 2, h, l, (h + l) / 2) for i, (h, l) in enumerate(zip(highs, lows))]
        swings = detect_swings(rows, 2, 2)
        low_swings = [s for s in swings if s.kind == "low"]
        high_swings = [s for s in swings if s.kind == "high"]
        self.assertGreaterEqual(len(low_swings), 2)
        self.assertGreaterEqual(len(high_swings), 2)
        self.assertEqual(low_swings[1].label, "HL")
        self.assertEqual(high_swings[1].label, "HH")
        self.assertEqual(low_swings[0].confirm_index, low_swings[0].index + 2)

    def test_structure_requires_confirmed_swings(self):
        rows = []
        # Two higher swing highs and two higher swing lows.
        points = [
            (10, 11, 9, 10), (10, 12, 9.5, 11), (11, 14, 10, 13), (13, 12.5, 10.5, 11),
            (11, 12, 10, 11), (11, 13, 10.5, 12), (12, 15, 11, 14), (14, 13.5, 11.5, 12),
            (12, 13, 12, 12.5), (12.5, 14, 12.5, 13.5),
        ]
        for i, (o, h, l, c) in enumerate(points):
            rows.append(candle(i * 900, o, h, l, c))
        swings = detect_swings(rows, 1, 1)
        structure, _ = structure_at(rows, swings, len(rows) - 1)
        self.assertIn(structure, {"bullish", "neutral"})


class TrialSafetyTests(unittest.TestCase):
    def make_trend(self, tf_seconds: int, count: int, start: float, step: float):
        rows = []
        price = start
        for i in range(count):
            o = price
            c = price + step
            rows.append(candle(i * tf_seconds, o, max(o, c) + 0.4, min(o, c) - 0.4, c))
            price = c
        return rows

    def test_trial_is_signal_only_and_never_invents_trade(self):
        m15 = self.make_trend(900, 80, 100, 0.2)
        h4 = self.make_trend(14400, 30, 100, 0.8)
        result = run_human_apostle_trial(m15, h4, symbol="TEST", account_login=123, now_ts=9999999)
        self.assertEqual(result["mode"], "SIGNAL_ONLY")
        self.assertIn("ORDER NOT EXECUTED", result["execution"])
        self.assertIsNone(result["proposed_trade"])

    def test_same_candle_shift_retest_is_disabled(self):
        m15 = self.make_trend(900, 80, 100, 0.2)
        h4 = self.make_trend(14400, 30, 100, 0.8)
        result = run_human_apostle_trial(m15, h4, symbol="TEST", account_login=123, now_ts=9999999)
        self.assertFalse(result["rules"]["same_candle_shift_retest"])
        self.assertTrue(result["retest"]["same_candle_blocked"])

    def test_trial_uses_fixed_apostle_timeframes(self):
        m15 = self.make_trend(900, 80, 100, 0.2)
        h4 = self.make_trend(14400, 30, 100, 0.8)
        result = run_human_apostle_trial(m15, h4, symbol="TEST", account_login=123, now_ts=9999999)
        self.assertEqual(result["execution_timeframe"], "M15")
        self.assertEqual(result["bias_timeframe"], "H4")

    def test_insufficient_candles_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least 25"):
            run_human_apostle_trial(self.make_trend(900, 10, 100, 0.1), self.make_trend(14400, 10, 100, 0.4), symbol="TEST", account_login=1, now_ts=9999999)


if __name__ == "__main__":
    unittest.main()
