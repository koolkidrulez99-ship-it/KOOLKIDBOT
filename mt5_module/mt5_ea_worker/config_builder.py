from __future__ import annotations

from pathlib import Path


VALID_TIMEFRAMES = {"M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15", "M20", "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12", "D1", "W1", "MN1"}


def build_config(path: Path, *, login: int, server: str | None = None, expert: str, preset: str | None, symbol: str, timeframe: str, allow_trading: bool, allow_dll: bool) -> None:
    timeframe = timeframe.upper()
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(f"Unsupported MT5 timeframe: {timeframe}")
    if not symbol.strip() or any(ch in symbol for ch in "\r\n=[]"):
        raise ValueError("Invalid MT5 symbol.")
    if server and any(ch in server for ch in "\r\n=[]"):
        raise ValueError("Invalid MT5 server name.")
    lines = ["[Common]", f"Login={int(login)}"]
    if server:
        lines.append(f"Server={server.strip()}")
    lines += ["", "[Experts]",
        f"AllowLiveTrading={1 if allow_trading else 0}", f"AllowDllImport={1 if allow_dll else 0}",
        "Enabled=1", "Account=0", "Profile=0", "", "[StartUp]",
        f"Expert={expert}", f"Symbol={symbol.strip()}", f"Period={timeframe}",
    ]
    if preset:
        lines.append(f"ExpertParameters={preset}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
