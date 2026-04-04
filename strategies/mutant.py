from strategies.unchain import (
    UnchainStrategy,
    _clean_unchain_duration_unit,
    _format_unchain_barrier,
)


def _clean_ntt_duration_unit(value):
    unit = _clean_unchain_duration_unit(value)
    return unit if unit in ("t", "m", "h") else "t"


def _sanitize_ntt_duration(value, duration_unit):
    unit = _clean_ntt_duration_unit(duration_unit)
    try:
        duration = int(float(value))
    except Exception:
        defaults = {"t": 5, "m": 2, "h": 1}
        duration = defaults.get(unit, 5)

    if unit == "t":
        return max(5, min(10, duration))
    if unit == "m":
        return max(2, min(59, duration))
    return max(1, min(24, duration))


def _format_ntt_barrier(raw_value, side, duration_unit):
    side_name = str(side or "").upper().strip()
    if side_name not in ("TOUCH", "NO_TOUCH"):
        side_name = "TOUCH"
    fallback = "+0.12"
    raw = str(raw_value if raw_value is not None else "").strip() or fallback
    if not raw.startswith(("+", "-")):
        raw = "+" + raw
    formatted = _format_unchain_barrier(raw, "HIGHER", duration_unit)
    try:
        numeric = float(str(formatted).strip())
    except Exception:
        numeric = 0.12
    return f"{'+' if numeric >= 0 else '-'}{abs(numeric):.2f}"


def _map_touch_bias_status(status):
    text = str(status or "").upper().strip()
    if "HIGHER" in text:
        return text.replace("HIGHER", "TOUCH")
    if "LOWER" in text:
        return text.replace("LOWER", "NO TOUCH")
    return text


class NTTStrategy(UnchainStrategy):
    """
    Mutant profile.

    This intentionally reuses UNCHAIN's mature market-reading engine for now,
    then remaps the output into Touch / No Touch wording until you decide on a
    more profile-specific scoring model later.
    """

    def get_bias_payload(self, config=None):
        config = config or {}
        mapped = {
            "higher_barrier": config.get("touch_barrier", config.get("higher_barrier", "+0.12")),
            "lower_barrier": config.get("no_touch_barrier", config.get("lower_barrier", "+0.12")),
            "duration": config.get("duration", 5),
            "duration_unit": _clean_ntt_duration_unit(config.get("duration_unit", "t")),
        }
        base = super().get_bias_payload(mapped) or {}
        touch_pct = float(base.get("higher_pct", 50.0) or 50.0)
        no_touch_pct = float(base.get("lower_pct", 50.0) or 50.0)
        reasons = list(base.get("reasons") or [])
        summary = str(base.get("summary") or "")
        summary = (
            summary.replace("Higher", "Touch")
            .replace("Lower", "No Touch")
            .replace("HIGHER", "TOUCH")
            .replace("LOWER", "NO TOUCH")
        )
        return {
            "status": _map_touch_bias_status(base.get("status")),
            "touch_pct": touch_pct,
            "no_touch_pct": no_touch_pct,
            "higher_pct": touch_pct,
            "lower_pct": no_touch_pct,
            "strength": base.get("strength", "Building"),
            "reasons": reasons,
            "lookback": int(base.get("lookback", 0) or 0),
            "summary": summary or "Gathering enough recent ticks to score Touch vs No Touch.",
            "updated_at": base.get("updated_at"),
            "range_width": float(base.get("range_width", 0.0) or 0.0),
            "range_pct": float(base.get("range_pct", 0.0) or 0.0),
            "shared_confidence": float(base.get("shared_confidence", 0.0) or 0.0),
            "touch_confidence": float(base.get("higher_confidence", 0.0) or 0.0),
            "no_touch_confidence": float(base.get("lower_confidence", 0.0) or 0.0),
        }

    def get_ui_payload(self):
        return {
            "profile": "NTT",
            "ntt": {
                "bias": self.get_bias_payload(),
                "last_price": self.last_price,
                "market_state": self.market_state,
                "signal_state": self.signal_state,
            },
        }

    def get_stats_payload(self, balance, session_start_balance):
        # Mutant should report settled profile performance only, not temporary
        # balance movement while a Touch/No Touch contract is still open.
        net_pnl = round(float(self.session_profit or 0.0), 2)
        total = int(self.total_wins) + int(self.total_losses)
        winrate = round((float(self.total_wins) / total) * 100, 1) if total else 0.0
        return {
            "balance": float(balance or 0.0),
            "net_pnl": net_pnl,
            "wins": int(self.total_wins),
            "losses": int(self.total_losses),
            "winrate": winrate,
            "session_profit": net_pnl,
            "profile_stats_label": "Mutant",
            "auto_trade": False,
        }
