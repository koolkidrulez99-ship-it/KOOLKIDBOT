from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

MAX_ACCOUNTS = 10

class ConnectRequest(BaseModel):
    account_id: str
    nickname: str = ""
    login: int
    broker: str = "MetaTrader 5"
    server: str = ""
    terminal_path: str = ""
    portable: bool = False
    password: str = ""
    remember_session: bool = True
    access_mode: Literal["trading", "investor"] = "trading"
    mode: Literal["real", "simulation"] = "real"
    symbol_aliases: Dict[str, str] = Field(default_factory=dict)

class CopyRequest(BaseModel):
    master_account_id: str
    slave_account_ids: List[str]
    lot_mode: Literal["same", "fixed", "multiplier", "equity_proportional"] = "same"
    fixed_lot: float = 0.01
    multiplier: float = 1.0
    trail_by_shoulders: bool = False
    risk_reward_ratio: float = 2.0
    shoulder_timeframe: Literal["M1", "M5", "M15", "M30", "H1"] = "M5"
    shoulder_strength: int = Field(default=2, ge=1, le=5)
    shoulder_buffer_points: float = Field(default=5.0, ge=0)
    limit_copied_trades: bool = False
    max_copied_trades_per_slave: int = Field(default=1, ge=1, le=100)
    source_filter: Literal["all", "manual", "ea", "magic"] = "all"
    magic_number: Optional[int] = None
    poll_ms: int = 300
    approval_required: bool = True

class CopyDecisionRequest(BaseModel):
    master_ticket: int
    should_copy: bool
    slave_account_ids: List[str] = Field(default_factory=list)

class ManualTradeRequest(BaseModel):
    target_account_ids: List[str]
    symbol: str
    side: Literal["buy", "sell"]
    volume: float
    sl: float = 0.0
    tp: float = 0.0
    ui_clicked_at: Optional[float] = None
    lot_mode: Literal["same", "fixed", "multiplier"] = "same"
    fixed_lot: float = 0.01
    multiplier: float = 1.0
    magic: int = 0
    comment: str = "KOOLKID"
    confirm_live: bool = False

class ModifyPositionRequest(BaseModel):
    account_id: str
    ticket: int
    sl: float = 0.0
    tp: float = 0.0

class PartialCloseRequest(BaseModel):
    account_id: str
    ticket: int
    volume: float

class MultiCloseRequest(BaseModel):
    targets: List[Dict[str, object]]
    ui_clicked_at: Optional[float] = None

class CloseRequest(BaseModel):
    account_id: str
    ticket: int
