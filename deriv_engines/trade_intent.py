from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TradeIntent:
    client_id: str
    req_id: Any
    profile: Optional[str]
    strategy_name: Optional[str]
    button: Optional[str]
    contract_type: str
    stake: float
    symbol: str
    barrier: Any = None
    barrier2: Any = None
    duration: int = 1
    duration_unit: str = "t"
    currency: str = "USD"
    mode: Optional[str] = None
    budget_reservation: Any = None
    req_meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request(cls, trade_request, *, state, req_id, stake, duration, duration_unit):
        trade_request = trade_request or {}
        return cls(
            client_id=trade_request.get("client_id"),
            req_id=req_id,
            profile=trade_request.get("profile"),
            strategy_name=trade_request.get("strategy_name"),
            button=trade_request.get("button"),
            contract_type=str(trade_request.get("contract_type") or "").strip(),
            stake=float(stake),
            symbol=str(trade_request.get("symbol") or state.get("current_symbol") or "R_10").strip(),
            barrier=trade_request.get("barrier"),
            barrier2=trade_request.get("barrier2"),
            duration=int(duration),
            duration_unit=str(duration_unit or "t").lower(),
            currency=str(trade_request.get("currency") or "USD"),
            mode=trade_request.get("mode"),
            budget_reservation=trade_request.get("budget_reservation"),
            req_meta=dict(trade_request.get("req_meta") or {}),
        )

