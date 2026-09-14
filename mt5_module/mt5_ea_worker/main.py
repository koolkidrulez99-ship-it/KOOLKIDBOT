from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

try:
    from .models import StartBotRequest
    from . import worker
except ImportError:  # direct `python main.py` execution
    from models import StartBotRequest
    import worker

app = FastAPI(title="KOOLKID Local MT5 EA Worker", version="1.0.0")


def require_worker_token(authorization: str | None = Header(default=None)):
    expected = os.getenv("MT5_WORKER_API_TOKEN", "").strip()
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid EA worker credentials.")


@app.get("/health")
def health():
    return {"ok": True, "service": "mt5-ea-worker", "revision": "mt5-ea-native-v5", "running": len([x for x in worker.reconcile() if x.get("status") == "running"]), "capabilities": {"start": True, "stop": True, "pause": False, "resume": False, "verified_ea_launch": True}}


@app.get("/terminals")
def terminals(_: None = Depends(require_worker_token)):
    return worker.terminals()


@app.get("/bots/running")
def running_bots(_: None = Depends(require_worker_token)):
    return [x for x in worker.reconcile() if x.get("status") in {"starting", "running"}]


@app.get("/bots")
def all_bots(_: None = Depends(require_worker_token)):
    return worker.reconcile()


@app.post("/bots/start")
def start_bot(payload: StartBotRequest, _: None = Depends(require_worker_token)):
    try:
        return worker.start_bot(payload)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/bots/{bot_id}/status")
def bot_status(bot_id: int, _: None = Depends(require_worker_token)):
    row = worker.get_bot(bot_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bot assignment not found.")
    return row


@app.post("/bots/{bot_id}/stop")
def stop_bot(bot_id: int, _: None = Depends(require_worker_token)):
    try:
        return worker.stop_bot(bot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0]))


@app.post("/bots/{bot_id}/pause")
def pause_bot(bot_id: int):
    raise HTTPException(status_code=409, detail="Pause is unavailable for arbitrary .ex5 EAs unless the EA exposes its own pause control.")


@app.post("/bots/{bot_id}/resume")
def resume_bot(bot_id: int):
    raise HTTPException(status_code=409, detail="Resume is unavailable for arbitrary .ex5 EAs. Start the stopped assignment again instead.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("MT5_EA_WORKER_HOST", "127.0.0.1"), port=int(os.getenv("MT5_EA_WORKER_PORT", "8001")))
