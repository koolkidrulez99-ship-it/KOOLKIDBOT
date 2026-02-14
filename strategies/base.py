from collections import deque, Counter

class BaseStrategy:
    def __init__(self):
        self.tick_count = 0
        self.tick_digits = deque(maxlen=100)
        self.digit_percentages = {i: 0 for i in range(10)}
        self.last_tick_digit = None

        self.trade_history = []
        self.last_trade_entry = {}

        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0

        self.auto_trade = False

        # Risk Controls
        self.tp = 0.0
        self.sl = 0.0
        self.auto_sl = True

        # Live session pnl tracker
        self.session_profit = 0.0

    def reset(self):
        self.tick_count = 0
        self.tick_digits.clear()
        self.digit_percentages = {i: 0 for i in range(10)}
        self.last_tick_digit = None

        self.trade_history = []
        self.last_trade_entry = {}

        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0

        self.auto_trade = False
        self.session_profit = 0.0

    def reset_tick_analysis(self):
        self.tick_count = 0
        self.tick_digits.clear()
        self.digit_percentages = {i: 0 for i in range(10)}
        self.last_tick_digit = None

    def clear_history(self):
        self.trade_history = []
        self.last_trade_entry = {}
        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.session_profit = 0.0

    def toggle_auto(self):
        self.auto_trade = not self.auto_trade
        return self.auto_trade

    def set_risk_controls(self, tp=0.0, sl=0.0, auto_sl=True):
        self.tp = float(tp)
        self.sl = float(sl)
        self.auto_sl = bool(auto_sl)

    def calculate_digit_percentages(self):
        if len(self.tick_digits) < 100:
            return {i: 0 for i in range(10)}

        counter = Counter(self.tick_digits)
        result = {}
        for digit in range(10):
            count = counter.get(digit, 0)
            pct = (count / 100) * 100
            result[digit] = round(pct, 1)
        return result

    def enforce_tp_sl(self):
        """
        Enforces TP/SL based on running session profit.
        """
        if self.tp > 0 and self.session_profit >= self.tp:
            self.auto_trade = False
            return "TP HIT"

        if self.sl > 0 and self.session_profit <= -abs(self.sl):
            self.auto_trade = False
            return "SL HIT"

        return None

    def on_tick(self, tick, digit):
        self.last_tick_digit = digit
        self.tick_count += 1
        self.tick_digits.append(digit)

        if self.tick_count == 100 or (self.tick_count > 100 and self.tick_count % 10 == 0):
            self.digit_percentages = self.calculate_digit_percentages()

        self.enforce_tp_sl()

    def on_contract(self, contract, balance):
        profit = float(contract.get("profit", 0))
        contract_type = contract.get("contract_type", "UNKNOWN")

        result = "WIN" if profit > 0 else "LOSS"

        if profit > 0:
            self.total_wins += 1
            self.total_profit += profit
        else:
            self.total_losses += 1
            self.total_loss += abs(profit)

        self.session_profit += profit

        self.last_trade_entry = {
            "time": contract.get("date_start", ""),
            "result": result,
            "profit": round(profit, 2),
            "contract_type": contract_type,
            "balance": round(balance, 2),
            "symbol": contract.get("underlying", "")
        }

        self.trade_history.append(self.last_trade_entry)
        if len(self.trade_history) > 200:
            self.trade_history.pop(0)

        self.enforce_tp_sl()

    def get_last_trade_entry(self):
        return self.last_trade_entry

    def get_ui_payload(self):
        return {
            "tick_count": self.tick_count,
            "last_digit": self.last_tick_digit,
            "percentages": self.digit_percentages,
            "confidence": {}
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
