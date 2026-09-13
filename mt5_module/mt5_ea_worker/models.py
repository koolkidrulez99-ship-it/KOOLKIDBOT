from __future__ import annotations

from pydantic import BaseModel, Field


class StartBotRequest(BaseModel):
    bot_id: int
    account_login: int
    account_type: str
    server: str | None = None
    symbol: str = Field(min_length=1, max_length=64)
    timeframe: str
    ea_path: str
    ea_filename: str
    preset_path: str | None = None
    preset_filename: str | None = None
    terminal_path: str | None = None
    bridge_terminal_path: str | None = None
    bridge_data_path: str | None = None
    allow_live: bool = False
    allow_dll: bool = False
    dll_required: bool = False
