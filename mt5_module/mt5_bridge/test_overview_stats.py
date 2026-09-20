from __future__ import annotations

from datetime import datetime, timedelta, timezone

import main


def _day(offset: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()


def _row(login: int, day: str, value: float) -> dict:
    return {
        "account_login": login,
        "close_time": f"{day}T12:00:00+00:00",
        "net_pl": value,
    }


def test_overview_series_populates_daily_and_equity():
    accounts = [
        {"login": 1, "equity": 1000.0},
        {"login": 2, "equity": 500.0},
    ]
    history = [
        _row(1, _day(-2), 100.0),
        _row(1, _day(-1), -50.0),
    ]
    equity, daily = main._overview_chart_series(accounts, history)
    assert daily[-1] == {"date": _day(0), "pl": 0.0}
    assert {row["date"]: row["pl"] for row in daily}[_day(-2)] == 100.0
    assert {row["date"]: row["pl"] for row in daily}[_day(-1)] == -50.0
    assert equity[-1]["date"] == _day(0)
    assert equity[-1]["equity"] == 1500.0
    assert len(equity) >= 3


def test_overview_equity_stops_before_impossible_balance_reset():
    accounts = [
        {"login": 1, "equity": 100.0},
        {"login": 2, "equity": 500.0},
    ]
    history = [
        _row(1, _day(-2), 1000.0),
        _row(1, _day(-1), 10.0),
        _row(2, _day(-2), 5.0),
    ]

    equity, daily = main._overview_chart_series(accounts, history)
    dates = [row["date"] for row in equity]
    assert _day(-2) not in dates
    assert dates[-1] == _day(0)
    assert daily[-1]["date"] == _day(0)
