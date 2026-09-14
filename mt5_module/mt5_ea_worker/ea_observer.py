from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRAITS = {
    "trendline": "Trendline logic",
    "breakout": "Breakout logic",
    "structure break": "Market-structure logic",
    "protected-structure": "Protected-structure logic",
    "bias": "Higher-timeframe bias",
    "spread": "Spread handling",
    "martingale": "Martingale behavior",
    "grid": "Grid behavior",
    "trailing": "Trailing-stop behavior",
    "scalp": "Scalping behavior",
}


def _log_files(data_dir: Path) -> list[Path]:
    files: list[Path] = []
    for folder in (data_dir / "logs", data_dir / "MQL5" / "Logs", data_dir / "MQL5" / "logs"):
        if folder.is_dir():
            files.extend(folder.glob("*.log"))
    return sorted(set(files), key=lambda path: (path.stat().st_mtime, str(path)))


def capture_log_offsets(data_dir: Path) -> dict[str, int]:
    offsets: dict[str, int] = {}
    for path in _log_files(data_dir):
        try:
            offsets[str(path.resolve())] = path.stat().st_size
        except OSError:
            pass
    return offsets


def _decode_log(data: bytes, from_offset: bool) -> str:
    if not data:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="ignore")
    if from_offset or b"\x00" in data[:64]:
        return data[: len(data) - (len(data) % 2)].decode("utf-16-le", errors="ignore")
    return data.decode("utf-8", errors="ignore")


def inspect_ea_logs(
    data_dir: Path,
    ea_filename: str,
    *,
    offsets: dict[str, int] | None = None,
    max_messages: int = 12,
) -> dict[str, Any]:
    stem = Path(ea_filename).stem.lower()
    relevant: list[str] = []
    success = False
    failure: str | None = None
    newest = 0.0

    for path in _log_files(data_dir):
        try:
            key = str(path.resolve())
            start = max(0, int((offsets or {}).get(key, 0)))
            with path.open("rb") as handle:
                handle.seek(start)
                text = _decode_log(handle.read(), start > 0)
            if not text:
                continue
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            continue

        for raw in text.splitlines():
            clean = " ".join(raw.replace("\x00", "").split())
            lowered = clean.lower()
            if stem not in lowered:
                continue
            relevant.append(clean[-500:])
            if "loaded successfully" in lowered or " initialized" in lowered:
                success = True
            if any(token in lowered for token in ("cannot load", "failed to load", "initialization failed", "init failed", "invalid ex5")):
                failure = clean[-500:]

    joined = " ".join(relevant).lower()
    timeframes = sorted(set(re.findall(r"\b(?:M[1-9]\d*|H[1-9]\d*|D1|W1|MN1)\b", joined.upper())))
    traits = [label for token, label in TRAITS.items() if token in joined]
    return {
        "ea_verified": bool(success and not failure),
        "verification_error": failure,
        "observed_messages": relevant[-max_messages:],
        "observed_timeframes": timeframes,
        "observed_traits": traits,
        "last_ea_activity": datetime.fromtimestamp(newest, timezone.utc).isoformat() if newest else None,
        "analysis_scope": "Observed MT5 logs only; compiled strategy source is not available.",
    }
