from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TERMINAL_ROOT = ROOT / "data" / "terminals"


def discover_terminals() -> list[dict[str, str]]:
    candidates: list[Path] = []
    configured = os.getenv("MT5_EA_TERMINAL_PATH", "").strip().strip('"')
    if configured:
        candidates.append(Path(configured))
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.getenv(env_name)
        if not base:
            continue
        root = Path(base)
        candidates.extend(root.glob("*/terminal64.exe"))
        candidates.extend(root.glob("*/*/terminal64.exe"))
    seen: set[str] = set()
    result = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen or not resolved.is_file():
            continue
        seen.add(key)
        result.append({"id": hashlib.sha256(key.encode()).hexdigest()[:12], "name": resolved.parent.name, "path": str(resolved)})
    return result


def select_terminal(requested: str | None) -> Path:
    if requested:
        path = Path(requested).expanduser().resolve()
        if path.name.lower() != "terminal64.exe" or not path.is_file():
            raise ValueError("Selected terminal64.exe was not found.")
        return path
    terminals = discover_terminals()
    if not terminals:
        raise ValueError("No MetaTrader 5 terminal64.exe installation was found. Set MT5_EA_TERMINAL_PATH for the EA worker.")
    if len(terminals) > 1:
        raise ValueError("Multiple MetaTrader 5 terminals were found. Select a terminal before starting the EA.")
    return Path(terminals[0]["path"])


def terminal_data_dir(terminal: Path) -> Path:
    configured = os.getenv("MT5_EA_DATA_PATH", "").strip().strip('"')
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("Configured MT5_EA_DATA_PATH does not exist.")
        return path
    appdata = os.getenv("APPDATA")
    if appdata:
        root = Path(appdata) / "MetaQuotes" / "Terminal"
        matches: list[Path] = []
        for origin in root.glob("*/origin.txt") if root.exists() else ():
            try:
                if str(terminal.parent).lower() in origin.read_text(encoding="utf-16", errors="ignore").lower() or str(terminal.parent).lower() in origin.read_text(encoding="utf-8", errors="ignore").lower():
                    matches.append(origin.parent)
            except OSError:
                continue
        if len(matches) == 1:
            return matches[0]
    portable = terminal.parent
    if (portable / "MQL5").is_dir() and os.access(portable, os.W_OK):
        return portable
    raise ValueError("MT5 data folder could not be identified. Set MT5_EA_DATA_PATH to an isolated terminal data directory.")


def prepare_dedicated_terminal(source_value: str, source_data_value: str | None, assignment_key: str) -> tuple[Path, Path]:
    source = Path(source_value).expanduser().resolve()
    if source.is_dir():
        source = source / "terminal64.exe"
    if source.name.lower() != "terminal64.exe" or not source.is_file():
        raise ValueError("The Windows execution server's MT5 terminal64.exe was not found.")
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", assignment_key).strip("._") or "assignment"
    target_dir = TERMINAL_ROOT / safe_key
    target = target_dir / "terminal64.exe"
    if not target.is_file():
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        # Never clone MT5's live runtime caches from an account terminal.
        # Bases/history files are commonly locked while MT5 is connected and
        # they are not required to launch an isolated EA terminal. Fresh logs
        # are also important so EA verification only observes this assignment.
        ignore_runtime = shutil.ignore_patterns(
            "Bases", "bases", "logs", "Logs", "Cache", "cache", "Tester", "tester",
        )
        shutil.copytree(source.parent, target_dir, dirs_exist_ok=True, ignore=ignore_runtime)
    source_data = Path(source_data_value).expanduser().resolve() if source_data_value else None
    saved_accounts = target_dir / "Config" / "accounts.dat"
    if source_data and source_data.is_dir() and not saved_accounts.is_file():
        source_config = source_data / "config"
        if source_config.is_dir():
            shutil.copytree(source_config, target_dir / "Config", dirs_exist_ok=True)
    if not target.is_file():
        raise RuntimeError("Could not prepare the dedicated MT5 terminal instance.")
    return target, target_dir
