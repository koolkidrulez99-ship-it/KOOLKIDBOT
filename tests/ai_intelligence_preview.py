"""Local-only synthetic dashboard for visual QA. No real Deriv connection."""
import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest
from flask import render_template, session, request, jsonify
from werkzeug.serving import run_simple

spec = importlib.util.spec_from_file_location("ai_tests", ROOT / "tests" / "test_ai_intelligence.py")
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
patch = pytest.MonkeyPatch()
temp = tempfile.TemporaryDirectory(prefix="koolkid-ai-preview-")
server = tests.server


@server.app.route("/__ai_preview")
def preview():
    current = server.clients.get("ai-test-alice")
    if not current or not current.get("ws_connected"):
        bot.client_for("alice")
        current = server.clients.get("ai-test-alice")
    history_count = max(0, min(2000, int(request.args.get("history") or 0)))
    if history_count and current:
        strategy = (current.get("strategies") or {}).get("KOOLKID")
        strategy.trade_history = [
            {
                "contract_id": str(index + 1),
                "profit": 0.8 if index % 2 == 0 else -1.0,
                "result": "WIN" if index % 2 == 0 else "LOSS",
                "stake": 1.0,
                "symbol": "R_25",
                "type": "EVEN",
                "sell_time": 1_800_000_000 + index,
            }
            for index in range(history_count)
        ]
        strategy.total_wins = (history_count + 1) // 2
        strategy.total_losses = history_count // 2
    session["user"] = "alice"
    session["client_id"] = "ai-test-alice"
    html = render_template("index.html", username="alice", license_context={"is_full_access": True, "is_lifetime": True},
                           mutant_access={"enabled": True}, active_broadcast_notice=None)
    if request.args.get("light") == "1":
        html = html.replace('<html lang="en">', '<html lang="en" data-theme="light">')
    return html


@server.app.route("/__ai_mobile")
def mobile():
    light = "1" if request.args.get("light") == "1" else "0"
    return f'''<!doctype html><html><body style="margin:0;background:#888">
    <button onclick="document.querySelector('iframe').contentDocument.querySelector('.ai-launcher').click()">Open mobile chat</button>
    <iframe title="Mobile dashboard" src="/__ai_preview?light={light}" style="display:block;width:390px;height:620px;border:0"></iframe>
    </body></html>'''


if __name__ == "__main__":
    bot = tests.bot.__wrapped__(patch, Path(temp.name))
    server.app.config["SESSION_COOKIE_NAME"] = "ai_preview_session"
    server.app.view_functions["disconnect"] = lambda: jsonify(status="connected", skipped=True)
    patch.setattr(server, "_is_ws_stale", lambda *a, **kw: False)
    run_simple("127.0.0.1", 5057, server.app, threaded=True, use_reloader=False)
