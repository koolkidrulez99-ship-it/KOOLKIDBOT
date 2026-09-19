from __future__ import annotations

import configparser
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import mq5_compiler

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "backtests"
JOBS_FILE = DATA_DIR / "jobs.json"
RESEARCH_FILE = DATA_DIR / "research.json"
MEMORY_FILE = DATA_DIR / "human_apostle_memory.json"
TERMINALS_ROOT = ROOT.parent / "mt5_multi_account" / "data" / "terminals"
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TEST_SECONDS = max(600, min(int(os.getenv("MT5_BACKTEST_MAX_SECONDS", "21600")), 43200))
_LOCK = threading.RLock()
_WORKER_LOCK = threading.RLock()
_WORKER: threading.Thread | None = None
_CURRENT_PROCESS: subprocess.Popen | None = None
_CURRENT_JOB_ID: str | None = None
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        return default


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _jobs() -> list[dict[str, Any]]:
    data = _load(JOBS_FILE, {"version": 1, "jobs": []})
    return list(data.get("jobs") or []) if isinstance(data, dict) else []


def _save_jobs(rows: list[dict[str, Any]]) -> None:
    _save(JOBS_FILE, {"version": 1, "jobs": rows})


def _research() -> list[dict[str, Any]]:
    data = _load(RESEARCH_FILE, {"version": 1, "items": []})
    return list(data.get("items") or []) if isinstance(data, dict) else []


def _save_research(rows: list[dict[str, Any]]) -> None:
    _save(RESEARCH_FILE, {"version": 1, "items": rows})
def _public_job(row: dict[str, Any]) -> dict[str, Any]:
    hidden = {"job_dir", "source_path", "preset_path", "terminal_path", "config_path", "process_id"}
    return {key: value for key, value in row.items() if key not in hidden}


def _find_job(job_id: str) -> dict[str, Any] | None:
    return next((row for row in _jobs() if row.get("id") == job_id), None)


def _update(job_id: str, **changes: Any) -> dict[str, Any]:
    with _LOCK:
        rows = _jobs()
        row = next((item for item in rows if item.get("id") == job_id), None)
        if not row:
            raise KeyError(job_id)
        row.update(changes)
        row["updated_at"] = _now()
        _save_jobs(rows)
        return dict(row)


def _source_terminal(workspace_id: str, account_login: int) -> Path:
    candidates = [
        TERMINALS_ROOT / f"{workspace_id}--session-{int(account_login)}",
        TERMINALS_ROOT / f"session-{int(account_login)}",
    ]
    for path in candidates:
        if (path / "terminal64.exe").is_file():
            return path
    raise RuntimeError(f"Backtest data terminal for MT5 account #{int(account_login)} is unavailable. Connect that account first.")


def _decode_log(path: Path) -> str:
    if not path.is_file():
        return ""
    raw = path.read_bytes()
    for encoding in ("utf-16", "utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")
def _tester_log_text(runtime: Path) -> str:
    files: list[Path] = []
    for folder in (runtime / "Tester" / "logs", runtime / "Logs"):
        if folder.is_dir():
            files.extend(folder.glob("*.log"))
    files.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    return "\n".join(_decode_log(path)[-20000:] for path in files[:3])


def _tester_percent(text: str) -> int | None:
    values = []
    for pattern in (r"\b(\d{1,3})\s*%", r"progress[^0-9]{0,20}(\d{1,3})"):
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = int(match.group(1))
            if 0 <= value <= 100:
                values.append(value)
    return max(values) if values else None


def _plain_report(path: Path) -> str:
    if not path.is_file():
        return ""
    raw = path.read_bytes()
    text = ""
    for encoding in ("utf-16", "utf-8-sig", "utf-8", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{2,}", "\n", text)
def _metric(text: str, labels: list[str]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:\n]\s*([^\n]+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _parse_number(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", value.replace("\xa0", " "))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _parse_report(path: Path) -> dict[str, Any]:
    text = _plain_report(path)
    if not text:
        return {}
    raw = {
        "net_profit": _metric(text, ["Total Net Profit", "Total net profit"]),
        "gross_profit": _metric(text, ["Gross Profit"]),
        "gross_loss": _metric(text, ["Gross Loss"]),
        "profit_factor": _metric(text, ["Profit Factor"]),
        "expected_payoff": _metric(text, ["Expected Payoff"]),
        "max_drawdown": _metric(text, ["Balance Drawdown Maximal", "Equity Drawdown Maximal"]),
        "total_trades": _metric(text, ["Total Trades"]),
        "profit_trades": _metric(text, ["Profit Trades (% of total)"]),
        "loss_trades": _metric(text, ["Loss Trades (% of total)"]),
        "largest_profit_trade": _metric(text, ["Largest profit trade"]),
        "largest_loss_trade": _metric(text, ["Largest loss trade"]),
    }
    summary: dict[str, Any] = {}
    for key, value in raw.items():
        parsed = _parse_number(value)
        summary[key] = parsed if parsed is not None else value
    return summary
def _source_observations(path: Path) -> list[str]:
    if path.suffix.lower() != ".mq5" or not path.is_file():
        return ["Compiled EX5 research: strategy logic is not decoded; only observed tester behavior and results are retained."]
    text = path.read_text(encoding="utf-8", errors="ignore")
    checks = [
        ("Moving-average logic detected", r"\biMA\s*\("),
        ("RSI filter detected", r"\biRSI\s*\("),
        ("ATR/volatility logic detected", r"\biATR\s*\("),
        ("MACD logic detected", r"\biMACD\s*\("),
        ("Bollinger-band logic detected", r"\biBands\s*\("),
        ("Market-structure/swing concepts detected", r"(?i)\b(swing|structure|HH|HL|LH|LL)\b"),
        ("Trendline concepts detected", r"(?i)trend\s*line|trendline"),
        ("Retest/rejection concepts detected", r"(?i)\b(retest|rejection)\b"),
        ("Risk-percent sizing concepts detected", r"(?i)risk\s*(percent|pct|%)"),
        ("Trailing-stop concepts detected", r"(?i)trail(?:ing)?\s*stop|trailing"),
    ]
    rows = [label for label, pattern in checks if re.search(pattern, text)]
    timeframes = sorted(set(re.findall(r"PERIOD_(M1|M5|M15|M30|H1|H4|D1|W1|MN1)", text)))
    if timeframes:
        rows.append("Referenced timeframes: " + ", ".join(timeframes))
    return rows[:20] or ["MQ5 source was available, but no supported high-level strategy markers were detected automatically."]

def _create_research(job: dict[str, Any], source_path: Path) -> None:
    if not job.get("research_opt_in") or job.get("status") != "complete":
        return
    with _LOCK:
        rows = _research()
        if any(item.get("job_id") == job["id"] for item in rows):
            return
        rows.insert(0, {
            "id": f"research-{uuid.uuid4().hex[:12]}",
            "job_id": job["id"],
            "workspace_id": job["workspace_id"],
            "username": job.get("username") or "user",
            "bot_filename": job.get("bot_filename"),
            "source_type": Path(str(job.get("bot_filename") or "")).suffix.lower().lstrip("."),
            "symbol": job.get("symbol"),
            "timeframe": job.get("timeframe"),
            "status": "pending",
            "created_at": _now(),
            "observations": _source_observations(source_path),
            "backtest": job.get("result") or {},
            "decision_note": None,
        })
        _save_research(rows)

def _cleanup_runtime(runtime: Path) -> None:
    try:
        shutil.rmtree(runtime, ignore_errors=True)
    except Exception:
        pass


def _copy_runtime(source: Path, runtime: Path) -> None:
    _cleanup_runtime(runtime)
    ignore = shutil.ignore_patterns("Logs", "logs", "Crash", "crash")
    shutil.copytree(source, runtime, ignore=ignore)


def _write_tester_config(job: dict[str, Any], runtime: Path, expert_rel: str, preset_name: str | None, report: Path) -> Path:
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config["Tester"] = {
        "Expert": expert_rel,
        "Symbol": str(job["symbol"]),
        "Period": str(job["timeframe"]),
        "Model": str(int(job.get("model") or 4)),
        "Optimization": "0",
        "FromDate": str(job["date_from"]).replace("-", "."),
        "ToDate": str(job["date_to"]).replace("-", "."),
        "ForwardMode": "0",
        "Deposit": str(float(job.get("deposit") or 10000)),
        "Currency": "USD",
        "Leverage": str(int(job.get("leverage") or 100)),
        "Report": str(report),
        "ReplaceReport": "1",
        "Visual": "0",
    }
    config["Tester"]["Shutdown" + "Terminal"] = "1"
    if preset_name:
        config["Tester"]["ExpertParameters"] = preset_name
    path = Path(job["job_dir"]) / "tester.ini"
    with path.open("w", encoding="utf-16") as handle:
        config.write(handle, space_around_delimiters=False)
    return path

def _run_tester(runtime: Path, config: Path) -> int:
    terminal = runtime / "terminal64.exe"
    if not terminal.is_file():
        raise RuntimeError("Dedicated MT5 Strategy Tester terminal is missing.")
    completed = subprocess.run(
        [str(terminal), "/portable", f"/config:{config}"],
        cwd=str(runtime),
        timeout=MAX_TEST_SECONDS,
        check=False,
    )
    return int(completed.returncode)

def _run(job_id: str) -> None:
    job = _find_job(job_id)
    if not job:
        return
    job_dir = Path(job["job_dir"])
    source = Path(job["source_path"])
    runtime = job_dir / "terminal"
    try:
        _update(job_id, status="preparing", stage="Preparing isolated MT5 tester", progress=8, started_at=_now(), error=None)
        executable = source
        if source.suffix.lower() == ".mq5":
            _update(job_id, status="compiling", stage="Compiling MQ5 on server", progress=14)
            compiled = mq5_compiler.compile_mq5(source.read_bytes(), source.name, job_dir / "compiled")
            if not compiled.get("success"):
                raise RuntimeError(f"MQ5 compilation failed: {compiled.get('errors')} error(s).")
            executable = Path(str(compiled["ex5_path"]))
            _update(
                job_id,
                compile={
                    "errors": compiled.get("errors"),
                    "warnings": compiled.get("warnings"),
                    "log": compiled.get("log", "")[-4000:],
                },
                progress=24,
            )
        source_terminal = _source_terminal(str(job["workspace_id"]), int(job["account_login"]))
        _update(job_id, status="preparing", stage="Cloning isolated Strategy Tester terminal", progress=28)
        _copy_runtime(source_terminal, runtime)
        expert_dir = runtime / "MQL5" / "Experts" / "KOOLKIDBacktests"
        expert_dir.mkdir(parents=True, exist_ok=True)
        expert_name = f"{job_id}{executable.suffix.lower()}"
        shutil.copy2(executable, expert_dir / expert_name)

        preset_name = None
        preset_path = Path(str(job.get("preset_path") or ""))
        if preset_path.is_file():
            tester_profiles = runtime / "MQL5" / "Profiles" / "Tester"
            tester_profiles.mkdir(parents=True, exist_ok=True)
            preset_name = f"{job_id}.set"
            shutil.copy2(preset_path, tester_profiles / preset_name)

        report = job_dir / "report.html"
        config = _write_tester_config(
            job,
            runtime,
            f"KOOLKIDBacktests\\{expert_name}",
            preset_name,
            report,
        )
        _update(
            job_id,
            status="testing",
            stage="MT5 Strategy Tester running",
            progress=40,
            config_path=str(config),
            terminal_path=str(runtime),
        )
        return_code = _run_tester(runtime, config)
        _update(
            job_id,
            status="analyzing",
            stage="Analyzing MT5 report",
            progress=93,
            return_code=return_code,
        )

        candidates = [report, job_dir / "report.htm"]
        report_path = next((path for path in candidates if path.is_file()), None)
        if report_path is None:
            found = list(job_dir.glob("report.*"))
            report_path = found[0] if found else None
        result = _parse_report(report_path) if report_path else {}
        log_tail = _tester_log_text(runtime)[-6000:]
        if not result and return_code != 0:
            raise RuntimeError(f"MT5 Strategy Tester exited with code {return_code}.")

        completed = _update(
            job_id,
            status="complete",
            stage="Complete",
            progress=100,
            completed_at=_now(),
            result=result,
            report_filename=report_path.name if report_path else None,
            tester_log=log_tail,
        )
        _create_research(completed, source)
    except Exception as exc:
        _update(
            job_id,
            status="failed",
            stage="Failed",
            progress=100,
            completed_at=_now(),
            error=str(exc),
        )
    finally:
        _cleanup_runtime(runtime)

def _worker_loop() -> None:
    global _WORKER
    while True:
        with _LOCK:
            queued = [row for row in _jobs() if row.get("status") == "queued"]
            queued.sort(key=lambda row: row.get("created_at") or "")
        if not queued:
            break
        _run(str(queued[0]["id"]))
    with _WORKER_LOCK:
        _WORKER = None


def ensure_worker() -> None:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER and _WORKER.is_alive():
            return
        _WORKER = threading.Thread(
            target=_worker_loop,
            name="koolkid-backtest-worker",
            daemon=True,
        )
        _WORKER.start()

def recover_jobs() -> None:
    with _LOCK:
        rows = _jobs()
        changed = False
        for row in rows:
            if row.get("status") in {"preparing", "compiling", "testing", "analyzing"}:
                row["status"] = "queued"
                row["stage"] = "Recovered after service restart"
                row["progress"] = min(int(row.get("progress") or 5), 30)
                row["updated_at"] = _now()
                changed = True
        if changed:
            _save_jobs(rows)
    ensure_worker()

def list_for_workspace(workspace_id: str) -> dict[str, Any]:
    with _LOCK:
        rows = [
            _public_job(row)
            for row in _jobs()
            if row.get("workspace_id") == workspace_id
        ]
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    active_status = {"queued", "preparing", "compiling", "testing", "analyzing"}
    active = next((row for row in rows if row.get("status") in active_status), None)
    return {
        "jobs": rows,
        "daily_limit": None,
        "available": active is None,
        "next_available_at": None,
        "active_job": active,
    }

def create_job(
    workspace_id: str,
    username: str,
    account_login: int,
    bot_filename: str,
    bot_data: bytes,
    preset_filename: str | None,
    preset_data: bytes | None,
    symbol: str,
    timeframe: str,
    date_from: str,
    date_to: str,
    deposit: float,
    leverage: int,
    model: int,
    research_opt_in: bool,
) -> dict[str, Any]:
    if not bot_filename.lower().endswith((".ex5", ".mq5")):
        raise ValueError("Choose an .ex5 or .mq5 MT5 bot.")
    if not bot_data or len(bot_data) > MAX_FILE_BYTES:
        raise ValueError("The bot file is empty or exceeds the 25 MB limit.")
    if preset_filename and not preset_filename.lower().endswith(".set"):
        raise ValueError("The optional preset must be a .set file.")
    with _LOCK:
        quota = list_for_workspace(workspace_id)
        if quota["active_job"]:
            raise RuntimeError("One backtest is already active for this user.")
        job_id = f"bt-{uuid.uuid4().hex[:12]}"
        job_dir = DATA_DIR / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(
            r"[^A-Za-z0-9._() -]+",
            "_",
            Path(bot_filename).name,
        ).strip(" .")
        source = job_dir / safe_name
        source.write_bytes(bot_data)
        preset_path = None
        if preset_data and preset_filename:
            preset_name = re.sub(
                r"[^A-Za-z0-9._() -]+",
                "_",
                Path(preset_filename).name,
            )
            preset_path = job_dir / preset_name
            preset_path.write_bytes(preset_data)
        row = {
            "id": job_id,
            "workspace_id": workspace_id,
            "username": username,
            "account_login": int(account_login),
            "bot_filename": safe_name,
            "bot_sha256": hashlib.sha256(bot_data).hexdigest(),
            "preset_filename": preset_path.name if preset_path else None,
            "symbol": symbol.strip(),
            "timeframe": timeframe.upper(),
            "date_from": date_from,
            "date_to": date_to,
            "deposit": float(deposit),
            "leverage": int(leverage),
            "model": int(model),
            "research_opt_in": bool(research_opt_in),
            "status": "queued",
            "stage": "Queued on server",
            "progress": 2,
            "created_at": _now(),
            "updated_at": _now(),
            "started_at": None,
            "completed_at": None,
            "result": {},
            "error": None,
            "job_dir": str(job_dir),
            "source_path": str(source),
            "preset_path": str(preset_path) if preset_path else None,
        }
        rows = _jobs()
        rows.append(row)
        _save_jobs(rows)
    ensure_worker()
    return _public_job(row)


def all_jobs() -> list[dict[str, Any]]:
    with _LOCK:
        rows = [_public_job(row) for row in _jobs()]
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return rows


def all_research() -> list[dict[str, Any]]:
    with _LOCK:
        rows = _research()
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return rows

def decide_research(item_id: str, decision: str, note: str | None = None) -> dict[str, Any]:
    if decision not in {"approve", "reject", "research"}:
        raise ValueError("Unsupported research decision.")
    with _LOCK:
        rows = _research()
        item = next((row for row in rows if row.get("id") == item_id), None)
        if not item:
            raise KeyError(item_id)
        item["status"] = {
            "approve": "approved_candidate",
            "reject": "rejected",
            "research": "keep_researching",
        }[decision]
        item["decision_at"] = _now()
        item["decision_note"] = note
        _save_research(rows)

        if decision == "approve":
            memory = _load(MEMORY_FILE, {"version": 1, "items": []})
            items = list(memory.get("items") or [])
            if not any(row.get("research_id") == item_id for row in items):
                items.insert(0, {
                    "research_id": item_id,
                    "approved_at": _now(),
                    "bot_filename": item.get("bot_filename"),
                    "symbol": item.get("symbol"),
                    "timeframe": item.get("timeframe"),
                    "observations": item.get("observations") or [],
                    "backtest": item.get("backtest") or {},
                    "status": "candidate_reference",
                })
                _save(
                    MEMORY_FILE,
                    {"version": 1, "items": items},
                )
        return dict(item)


recover_jobs()
