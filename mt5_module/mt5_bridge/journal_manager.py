from __future__ import annotations

import json
import threading
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import multi_account_client
from hub_auth import current_workspace
from store import read_state

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "journal_archive.json"
_LOCK = threading.RLock()
_NOTES_LOCK = threading.RLock()


def _notes_file() -> Path:
    return ROOT / "data" / "workspaces" / current_workspace() / "journal_notes.json"
JOURNAL_TIMEZONE = timezone(timedelta(hours=-5))


def journal_today() -> date:
    return datetime.now(JOURNAL_TIMEZONE).date()


MOTIVATIONS = [
    "Protect the account first. Opportunity will still be there tomorrow.",
    "A clean setup is worth more than ten forced trades.",
    "Consistency compounds long before profits do.",
    "Patience is a position too.",
    "Trade the plan, not the pressure.",
    "One disciplined decision can protect a whole week.",
    "Good traders wait for clarity instead of chasing excitement.",
    "Small controlled losses keep you available for the next opportunity.",
    "The goal is not more trades. The goal is better decisions.",
    "Confidence comes from following your process.",
    "Let the market come to your level.",
    "A flat day is better than a forced loss.",
    "Protecting capital is part of making capital.",
    "You do not need every move. You need your move.",
    "Review the process before judging the outcome.",
    "Risk small enough to think clearly.",
    "The best trade can be the one you skip.",
    "Stay patient when nothing is there.",
    "A strong routine beats a lucky streak.",
    "Discipline makes good setups repeatable.",
    "Focus on execution, not excitement.",
    "Your edge needs patience more than prediction.",
    "Trade what happened, not what you hoped would happen.",
    "One good setup is enough for today.",
    "Do not let one loss change a good plan.",
    "Keep the next decision independent from the last result.",
    "Calm execution is an advantage.",
    "Wait for confirmation. Missing a trade costs less than forcing one.",
    "Protect your downside and let your edge do the rest.",
    "The chart owes you nothing. Follow your rules.",
    "A consistent trader is built one session at a time.",
    "Progress is cleaner when risk stays controlled.",
    "No setup means no trade.",
    "Do not confuse activity with productivity.",
    "The market rewards patience more often than urgency.",
    "Your risk plan matters most when emotions get loud.",
    "A disciplined reset is stronger than revenge trading.",
    "Good trading can feel boring. That is often a good sign.",
    "Judge yourself by the quality of the decision.",
    "Protect focus the same way you protect capital.",
    "You can always trade tomorrow if you protect today.",
    "The cleanest setups rarely need convincing.",
    "Let data improve your confidence, not your ego.",
    "A controlled session is a successful session.",
    "Your process should survive both wins and losses.",
    "Wait for your conditions, then act without hesitation.",
    "One mistake does not need a second mistake.",
    "Better entries begin with better patience.",
    "Risk is the part you control.",
    "Trading less can improve trading more.",
    "Do not chase what already left.",
    "Review, adjust, then reset.",
    "A red day can still be a good day if rules were followed.",
    "Keep your size small enough to stay objective.",
    "Let consistency build the confidence.",
    "Your next trade does not need to recover the last one.",
    "The plan is strongest when you follow it under pressure.",
    "Clear thinking is part of your edge.",
    "Make the trade earn your risk.",
    "The market will open again. Protect your account.",
    "Strong traders know when to stop.",
    "Do not turn a good setup into a bad risk.",
    "A plan followed is progress.",
    "Keep learning from the days that feel ordinary.",
    "Protect the downside before dreaming about the upside.",
    "The best improvement is often one repeated discipline.",
    "A quiet chart does not require a loud decision.",
    "Your edge is worthless without risk control.",
    "Do the same good things long enough for the numbers to matter.",
    "Trade with a reason you can explain later.",
    "A journal turns experience into evidence.",
    "Let your records tell you what to improve.",
    "Good habits make hard days easier.",
    "Do not increase risk to fix frustration.",
    "The next clean setup deserves a clear mind.",
    "Your account grows when discipline survives losing days.",
    "Be selective enough that every trade has a reason.",
    "A strong trader can sit still.",
    "Your rules should decide before emotions arrive.",
    "Keep the process simple enough to repeat.",
    "A missed trade is not a loss.",
    "Know when your best decision is to close the platform.",
    "A good month is built from controlled days.",
    "Track what works, remove what does not.",
    "No single trade defines your ability.",
    "Be consistent before trying to be aggressive.",
    "The market does not reward impatience on demand.",
    "Your journal is where confidence becomes measurable.",
    "Focus on what you can repeat.",
    "Protect tomorrow's capital today.",
]

def _load() -> dict[str, Any]:
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 1, "accounts": {}}
    except Exception:
        return {"version": 1, "accounts": {}}


def _save(data: dict[str, Any]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)


def motivation_for(day: date) -> str:
    return MOTIVATIONS[(day.toordinal() - 1) % len(MOTIVATIONS)]


def _load_notes() -> dict[str, str]:
    path = _notes_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw = data.get("notes") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if isinstance(value, str) and value.strip()}


def _save_notes(notes: dict[str, str]) -> None:
    path = _notes_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "notes": notes, "updated_at": datetime.now(timezone.utc).isoformat()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _parse_note_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("Journal note date must use YYYY-MM-DD.") from exc
    if parsed.year < 2010 or parsed > journal_today() + timedelta(days=1):
        raise ValueError("Journal note date is outside the supported range.")
    return parsed


def note_for(day_value: date | str) -> str:
    day = day_value if isinstance(day_value, date) else _parse_note_date(day_value)
    with _NOTES_LOCK:
        return _load_notes().get(day.isoformat(), "")


def save_note(day_value: str, text: str) -> dict[str, Any]:
    day = _parse_note_date(day_value)
    clean = str(text or "").strip()
    if len(clean) > 5000:
        raise ValueError("Journal note is too long. Keep it under 5000 characters.")
    with _NOTES_LOCK:
        notes = _load_notes()
        if clean:
            notes[day.isoformat()] = clean
        else:
            notes.pop(day.isoformat(), None)
        _save_notes(notes)
    return {"date": day.isoformat(), "note": clean}


def _close_date(row: dict[str, Any]) -> date | None:
    raw = str(row.get("close_time") or "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _trade_key(row: dict[str, Any]) -> str:
    return "|".join([
        str(row.get("ticket") or row.get("id") or ""),
        str(row.get("close_time") or ""),
        str(row.get("symbol") or ""),
        str(row.get("volume") or ""),
    ])

def _account_exists(account_login: int) -> dict[str, Any]:
    profile = next(
        (row for row in read_state().get("profiles", []) if int(row.get("login") or 0) == int(account_login)),
        None,
    )
    if not profile:
        raise ValueError(f"MT5 account #{int(account_login)} is not part of this workspace.")
    return profile


def _refresh_archive(account_login: int, year: int) -> tuple[bool, str | None]:
    today = journal_today()
    start = date(max(2010, min(year, today.year)), 1, 1)
    days = max(30, (today - start).days + 7) if start <= today else 30
    days = min(days, 3650)
    try:
        rows = multi_account_client.account_request(account_login, f"/history?days={days}", timeout=20)
    except RuntimeError as exc:
        return False, str(exc)

    with _LOCK:
        data = _load()
        accounts = data.setdefault("accounts", {})
        key = str(int(account_login))
        bucket = accounts.setdefault(key, {"trades": {}, "updated_at": None})
        trades = bucket.setdefault("trades", {})
        for row in rows or []:
            close_day = _close_date(row)
            if close_day is None:
                continue
            normalized = dict(row)
            normalized["account_login"] = int(account_login)
            trades[_trade_key(normalized)] = normalized
        bucket["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save(data)
    return True, None

def _archived_rows(account_login: int) -> tuple[list[dict[str, Any]], str | None]:
    with _LOCK:
        data = _load()
        bucket = (data.get("accounts") or {}).get(str(int(account_login))) or {}
        trades = bucket.get("trades") or {}
        rows = [dict(row) for row in trades.values() if isinstance(row, dict)]
        rows.sort(key=lambda row: str(row.get("close_time") or ""))
        return rows, bucket.get("updated_at")


def _daily_summary(rows: list[dict[str, Any]], day: date, note: str = "") -> dict[str, Any]:
    pnl = sum(float(row.get("net_pl") or 0) for row in rows)
    wins = sum(1 for row in rows if float(row.get("net_pl") or 0) > 0)
    losses = sum(1 for row in rows if float(row.get("net_pl") or 0) < 0)
    return {
        "date": day.isoformat(),
        "day": day.day,
        "pnl": round(pnl, 2),
        "trades": len(rows),
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / len(rows) * 100), 1) if rows else 0.0,
        "motivation": motivation_for(day) if day <= journal_today() else None,
        "note": note,
        "trade_rows": rows,
    }

def month_view(account_login: int, year: int, month: int) -> dict[str, Any]:
    profile = _account_exists(account_login)
    if month < 1 or month > 12:
        raise ValueError("Month must be between 1 and 12.")
    refreshed, refresh_error = _refresh_archive(account_login, year)
    archived, updated_at = _archived_rows(account_login)
    grouped: dict[date, list[dict[str, Any]]] = {}
    for row in archived:
        day = _close_date(row)
        if day and day.year == year and day.month == month:
            grouped.setdefault(day, []).append(row)

    days_in_month = monthrange(year, month)[1]
    with _NOTES_LOCK:
        notes = _load_notes()
    days = [
        _daily_summary(
            grouped.get(date(year, month, number), []),
            date(year, month, number),
            notes.get(date(year, month, number).isoformat(), ""),
        )
        for number in range(1, days_in_month + 1)
    ]
    trade_days = [day for day in days if day["trades"] > 0]
    total_trades = sum(day["trades"] for day in trade_days)
    wins = sum(day["wins"] for day in trade_days)
    losses = sum(day["losses"] for day in trade_days)
    net = round(sum(day["pnl"] for day in trade_days), 2)
    best = max(trade_days, key=lambda day: day["pnl"], default=None)
    worst = min(trade_days, key=lambda day: day["pnl"], default=None)
    today = journal_today()
    return {
        "account": {
            "login": int(account_login),
            "nickname": profile.get("nickname"),
            "broker": profile.get("broker"),
            "server": profile.get("server"),
            "currency": profile.get("currency") or "USD",
        },
        "view": "month",
        "year": year,
        "month": month,
        "days": days,
        "summary": {
            "net_pnl": net,
            "trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round((wins / total_trades * 100), 1) if total_trades else 0.0,
            "winning_days": sum(1 for day in trade_days if day["pnl"] > 0),
            "losing_days": sum(1 for day in trade_days if day["pnl"] < 0),
            "best_day": best,
            "worst_day": worst,
            "average_day_pnl": round(net / len(trade_days), 2) if trade_days else 0.0,
        },
        "today": today.isoformat(),
        "today_motivation": motivation_for(today),
        "archive_updated_at": updated_at,
        "live_refresh": refreshed,
        "refresh_error": refresh_error,
    }

def year_view(account_login: int, year: int) -> dict[str, Any]:
    profile = _account_exists(account_login)
    refreshed, refresh_error = _refresh_archive(account_login, year)
    archived, updated_at = _archived_rows(account_login)
    months = []
    for month in range(1, 13):
        month_rows = []
        for row in archived:
            day = _close_date(row)
            if day and day.year == year and day.month == month:
                month_rows.append(row)
        pnl = round(sum(float(row.get("net_pl") or 0) for row in month_rows), 2)
        wins = sum(1 for row in month_rows if float(row.get("net_pl") or 0) > 0)
        losses = sum(1 for row in month_rows if float(row.get("net_pl") or 0) < 0)
        months.append({
            "month": month,
            "pnl": pnl,
            "trades": len(month_rows),
            "wins": wins,
            "losses": losses,
            "win_rate": round((wins / len(month_rows) * 100), 1) if month_rows else 0.0,
        })
    total_trades = sum(item["trades"] for item in months)
    wins = sum(item["wins"] for item in months)
    losses = sum(item["losses"] for item in months)
    return {
        "account": {
            "login": int(account_login),
            "nickname": profile.get("nickname"),
            "broker": profile.get("broker"),
            "server": profile.get("server"),
            "currency": profile.get("currency") or "USD",
        },
        "view": "year",
        "year": year,
        "months": months,
        "summary": {
            "net_pnl": round(sum(item["pnl"] for item in months), 2),
            "trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round((wins / total_trades * 100), 1) if total_trades else 0.0,
            "profitable_months": sum(1 for item in months if item["pnl"] > 0),
            "losing_months": sum(1 for item in months if item["pnl"] < 0),
        },
        "archive_updated_at": updated_at,
        "live_refresh": refreshed,
        "refresh_error": refresh_error,
    }
