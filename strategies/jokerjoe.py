from collections import deque, Counter
from datetime import datetime


class JokerJoeStrategy:
    def __init__(self):
        self.reset()

    def reset(self):
        self.tick_count = 0
        self.tick_digits = deque(maxlen=100)
        self.digit_percentages = {i: 0 for i in range(10)}
        self.last_tick_digit = None

        self.trade_history = []

        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0

        # AI Engine confidence
        self.match_confidence = 0
        self.diff_confidence = 0

        self.pattern_buffer = deque(maxlen=10)

        self.auto_trade = False
        self.last_trade_entry = None

    def reset_tick_analysis(self):
        self.tick_count = 0
        self.tick_digits.clear()
        self.digit_percentages = {i: 0 for i in range(10)}
        self.last_tick_digit = None
        self.pattern_buffer.clear()

    def round_to_nearest_5(self, x):
        return int(5 * round(float(x) / 5))

    def now_time(self):
        return datetime.now().strftime("%H:%M:%S")

    def calculate_digit_percentages(self):
        if len(self.tick_digits) < 100:
            return {i: 0 for i in range(10)}

        counter = Counter(self.tick_digits)
        result = {}

        for digit in range(10):
            count = counter.get(digit, 0)
            pct = (count / 100) * 100
            result[digit] = self.round_to_nearest_5(pct)

        return result

    def update_ai_engine(self):
        if len(self.pattern_buffer) < 5:
            return

        last = list(self.pattern_buffer)

        repeats = 0
        for i in range(1, len(last)):
            if last[i] == last[i - 1]:
                repeats += 1

        # AI logic: repeats favor MATCHES
        if repeats >= 2:
            self.match_confidence = min(100, self.match_confidence + 12)
            self.diff_confidence = max(0, self.diff_confidence - 6)
        else:
            self.diff_confidence = min(100, self.diff_confidence + 10)
            self.match_confidence = max(0, self.match_confidence - 5)

    def toggle_auto(self):
        self.auto_trade = not self.auto_trade
        return self.auto_trade

    def on_tick(self, tick, digit):
        self.last_tick_digit = digit
        self.pattern_buffer.append(digit)

        self.tick_count += 1
        self.tick_digits.append(digit)

        if self.tick_count == 100 or (self.tick_count > 100 and self.tick_count % 10 == 0):
            self.digit_percentages = self.calculate_digit_percentages()

        self.update_ai_engine()

    def on_contract(self, contract, balance):
        if not (contract.get("is_sold") or contract.get("is_settled")):
            return

        profit = float(contract.get("profit", 0))
        buy_price = float(contract.get("buy_price", 0))
        contract_type = contract.get("contract_type", "UNKNOWN")

        result = "WIN" if profit > 0 else "LOSS"

        if profit > 0:
            self.total_wins += 1
            self.total_profit += profit
        else:
            self.total_losses += 1
            self.total_loss += abs(profit)

        entry = {
            "time": self.now_time(),
            "result": result,
            "profit": round(profit, 2),
            "contract_type": contract_type,
            "buy_price": round(buy_price, 2),
            "balance": round(balance, 2),
            "symbol": contract.get("underlying", "")
        }

        self.trade_history.append(entry)
        if len(self.trade_history) > 200:
            self.trade_history.pop(0)

        self.last_trade_entry = entry

    def get_last_trade_entry(self):
        return self.last_trade_entry or {}

    def clear_history(self):
        self.trade_history = []
        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0

    def get_ui_payload(self):
        return {
            "tick_count": self.tick_count,
            "last_digit": self.last_tick_digit,
            "percentages": self.digit_percentages,
            "ai_engine": {
                "matches": self.match_confidence,
                "differs": self.diff_confidence
            }
        }

    def get_stats_payload(self, balance, session_start_balance):
        total_trades = self.total_wins + self.total_losses
        winrate = (self.total_wins / total_trades * 100) if total_trades > 0 else 0
        loserate = (self.total_losses / total_trades * 100) if total_trades > 0 else 0
        net_pnl = self.total_profit - self.total_loss

        session_pnl = 0
        if session_start_balance is not None:
            session_pnl = balance - session_start_balance

        return {
            "balance": round(balance, 2),
            "wins": self.total_wins,
            "losses": self.total_losses,
            "winrate": round(winrate, 1),
            "loserate": round(loserate, 1),
            "total_profit": round(self.total_profit, 2),
            "total_loss": round(self.total_loss, 2),
            "net_pnl": round(net_pnl, 2),
            "session_pnl": round(session_pnl, 2),
            "auto_trade": self.auto_trade
        }
