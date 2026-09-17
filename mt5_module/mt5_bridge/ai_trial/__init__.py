"""KOOLKID AI Intelligence trial package.

Session 1 is deliberately signal-only. It reads MT5 candles and never submits,
modifies, or closes an order.
"""

from .engine import run_human_apostle_trial
from .storage import clear_snapshot, load_snapshot, save_snapshot

__all__ = ["run_human_apostle_trial", "clear_snapshot", "load_snapshot", "save_snapshot"]
