from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class NativeSignal:
    strategy_key: str
    strategy_name: str
    title: str
    decision: str = "WAIT"
    stage: str = "SCANNING"
    score: float = 0.0
    reason: str = "No setup"
    direction: str | None = None
    entry: float | None = None
    sl: float | None = None
    tp: float | None = None
    risk_percent: float | None = None
    source_time: int | None = None
    signal_key: str | None = None
    rules: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.decision in {"BUY", "SELL"} and self.entry is not None and self.sl is not None and self.tp is not None

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["valid"] = self.valid
        return row
