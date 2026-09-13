import unittest
from mt5_multi_account.worker import filling_candidates, send_market_order


class Result:
    def __init__(self, retcode, comment=""):
        self.retcode = retcode
        self.comment = comment

    def _asdict(self):
        return {"retcode": self.retcode, "comment": self.comment}


class FakeMt5:
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_INVALID_FILL = 10030

    def __init__(self, accepted):
        self.accepted = accepted
        self.attempts = []

    def order_check(self, request):
        return Result(0)

    def order_send(self, request):
        filling = request["type_filling"]
        self.attempts.append(filling)
        return Result(10009, "done") if filling == self.accepted else Result(10030, "Unsupported filling mode")

    def last_error(self):
        return (0, "ok")


class FillingModeTests(unittest.TestCase):
    def test_symbol_fok_is_preferred(self):
        mt5 = FakeMt5(FakeMt5.ORDER_FILLING_FOK)
        result = send_market_order(mt5, {"symbol": "Volatility 15 Index"}, {"filling_mode": FakeMt5.SYMBOL_FILLING_FOK})
        self.assertEqual(result["retcode"], 10009)
        self.assertEqual(mt5.attempts, [FakeMt5.ORDER_FILLING_FOK])

    def test_invalid_fill_retries_other_modes(self):
        mt5 = FakeMt5(FakeMt5.ORDER_FILLING_FOK)
        result = send_market_order(mt5, {"symbol": "Volatility 15 Index"}, {"filling_mode": 0})
        self.assertEqual(result["retcode"], 10009)
        self.assertEqual(mt5.attempts, [FakeMt5.ORDER_FILLING_IOC, FakeMt5.ORDER_FILLING_FOK])

if __name__ == "__main__":
    unittest.main()
