from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Any

_COMPILE_LOCK = threading.Lock()
DEFAULT_TIMEOUT = max(10, min(int(os.getenv("MT5_COMPILE_TIMEOUT_SECONDS", "45")), 120))


def _decode_log(path: Path) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    for encoding in ("utf-16", "utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def _metaeditor_command() -> list[str]:
    raw = os.getenv("MT5_METAEDITOR_CMD", "").strip()
    if raw:
        return shlex.split(raw, posix=os.name != "nt")
    configured = os.getenv("MT5_METAEDITOR_PATH", "").strip().strip('"')
    candidates = [configured] if configured else []
    if os.name == "nt":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.getenv(env_name)
            if root:
                candidates.append(str(Path(root) / "MetaTrader 5" / "MetaEditor64.exe"))
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        if os.name == "nt":
            return [candidate]
        # Production runs MT5/MetaEditor through Wine on a private Xvfb display,
        # so users never need MetaEditor installed or visible on their device.
        wine = os.getenv("MT5_WINE_BIN", "wine64").strip() or "wine64"
        xvfb = os.getenv("MT5_XVFB_BIN", "xvfb-run").strip() or "xvfb-run"
        return [xvfb, "-a", wine, candidate]
    return []


def compiler_status() -> dict[str, Any]:
    command = _metaeditor_command()
    return {
        "available": bool(command),
        "engine": "MetaEditor 5",
        "server_side": True,
        "timeout_seconds": DEFAULT_TIMEOUT,
    }


def _editor_path(path: Path) -> str:
    absolute = str(path.resolve())
    if os.name == "nt":
        return absolute
    # Wine exposes the Linux filesystem as Z: by default.
    return "Z:" + absolute.replace("/", "\\")


def _result_counts(log_text: str) -> tuple[int | None, int | None]:
    matches = list(re.finditer(r"(\d+)\s+errors?\s*,\s*(\d+)\s+warnings?", log_text, re.IGNORECASE))
    if not matches:
        return None, None
    match = matches[-1]
    return int(match.group(1)), int(match.group(2))


def compile_mq5(data: bytes, filename: str, output_dir: Path) -> dict[str, Any]:
    if not filename.lower().endswith(".mq5"):
        raise ValueError("Expected an .mq5 source file.")
    command = _metaeditor_command()
    if not command:
        raise RuntimeError("MetaEditor compiler is not configured on this server.")

    output_dir.mkdir(parents=True, exist_ok=True)
    source = output_dir / Path(filename).name
    ex5 = source.with_suffix(".ex5")
    log = output_dir / f"{source.stem}.compile.log"
    source.write_bytes(data)
    ex5.unlink(missing_ok=True)
    log.unlink(missing_ok=True)

    args = [
        *command,
        f"/compile:{_editor_path(source)}",
        f"/log:{_editor_path(log)}",
    ]
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    if not _COMPILE_LOCK.acquire(blocking=False):
        raise RuntimeError("The MT5 compiler is busy. Try again in a moment.")
    try:
        process = subprocess.run(
            args,
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            startupinfo=startupinfo,
            creationflags=creationflags,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"MQ5 compilation exceeded the {DEFAULT_TIMEOUT}s server limit.") from exc
    finally:
        _COMPILE_LOCK.release()

    log_text = _decode_log(log)
    errors, warnings = _result_counts(log_text)
    success = ex5.is_file() and ex5.stat().st_size > 0 and (errors in (None, 0))
    return {
        "success": success,
        "source_filename": source.name,
        "ex5_filename": ex5.name if success else None,
        "ex5_path": str(ex5) if success else None,
        "errors": errors if errors is not None else (0 if success else 1),
        "warnings": warnings if warnings is not None else 0,
        "return_code": int(process.returncode),
        "log": log_text[-12000:],
        "stdout": (process.stdout or "")[-2000:],
        "stderr": (process.stderr or "")[-2000:],
    }
