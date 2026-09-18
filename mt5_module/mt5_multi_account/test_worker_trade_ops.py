from __future__ import annotations

import multiprocessing as mp

from .worker import run_worker


def call(command_q, response_q, rid, op, payload=None):
    command_q.put({"id": rid, "op": op, "payload": payload or {}})
    while True:
        row = response_q.get(timeout=5)
        if row.get("id") == rid:
            if not row.get("ok"):
                raise AssertionError(row.get("error"))
            return row.get("result")


def run() -> None:
    command_q, response_q = mp.Queue(), mp.Queue()
    config = {"mode": "simulation", "login": 12345, "server": "KOOLKID-SIM"}
    proc = mp.Process(target=run_worker, args=(config, "", command_q, response_q), daemon=True)
    proc.start()
    startup = response_q.get(timeout=5)
    assert startup["id"] == "__startup__" and startup["ok"]
    opened = call(command_q, response_q, "open", "open_trade", {
        "symbol": "XAUUSD", "side": "buy", "volume": 0.20,
        "sl": 95.0, "tp": 110.0, "magic": 26033177, "comment": "KKN1000:test",
    })
    ticket = int(opened["ticket"])
    rows = call(command_q, response_q, "pos1", "positions")
    pos = next(row for row in rows if int(row["ticket"]) == ticket)
    assert abs(float(pos["volume"]) - 0.20) < 1e-9
    assert int(pos["magic"]) == 26033177
    assert str(pos["comment"]).startswith("KKN1000")

    modified = call(command_q, response_q, "mod", "modify_position", {"ticket": ticket, "sl": 100.0, "tp": 111.0})
    assert modified["modified"] is True
    pos = next(row for row in call(command_q, response_q, "pos2", "positions") if int(row["ticket"]) == ticket)
    assert float(pos["sl"]) == 100.0 and float(pos["tp"]) == 111.0
    partial = call(command_q, response_q, "partial", "close_partial", {"ticket": ticket, "volume": 0.10})
    assert partial["partial"] is True
    pos = next(row for row in call(command_q, response_q, "pos3", "positions") if int(row["ticket"]) == ticket)
    assert abs(float(pos["volume"]) - 0.10) < 1e-9

    try:
        call(command_q, response_q, "badpartial", "close_partial", {"ticket": ticket, "volume": 0.10})
        raise AssertionError("Full-size partial close was accepted")
    except AssertionError as exc:
        if str(exc) == "Full-size partial close was accepted":
            raise

    closed = call(command_q, response_q, "close", "close_position", {"ticket": ticket})
    assert closed["closed"] is True
    assert not call(command_q, response_q, "pos4", "positions")
    call(command_q, response_q, "stop", "shutdown")
    proc.join(timeout=5)
    assert not proc.is_alive()


if __name__ == "__main__":
    run()
    print("worker trade operation checks passed")
