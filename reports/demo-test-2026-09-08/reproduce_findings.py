"""Offline reproductions only. No broker connections or application writes."""
import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from strategies.human import HumanStrategy

tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8-sig"))


def load_function(name, namespace):
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "server.py", "exec"), namespace)
    return namespace[name]


strategy = HumanStrategy()
previous = {"contract_id": "previous-fall", "contract_type": "PUT", "status": "won", "profit": 0.31, "buy_price": 0.35}
current = {"contract_id": "current-rise", "contract_type": "CALL", "status": "open", "is_expired": 1, "is_sold": 0, "profit": -0.35, "buy_price": 0.35}
strategy.on_contract(previous, 100)
fast = load_function("_is_contract_settled_fast", {})
server_accepts = fast(current)
strategy.on_contract(current, 99.65)
stale_entry = strategy.get_last_trade_entry()
human = {
    "case": "expired_open_contract_settlement",
    "fixture": "representative expired/open response, not a captured full broker frame",
    "server_accepts_as_settled": server_accepts,
    "expected_entry_contract_id": current["contract_id"],
    "actual_entry_contract_id": stale_entry["contract_id"],
    "actual_entry_contract_type": stale_entry["contract_type"],
    "bug_reproduced": server_accepts and stale_entry["contract_id"] != current["contract_id"],
}

workers = []
clients = {}
namespace = {
    "clients": clients,
    "cloud_manager": SimpleNamespace(session_keys=lambda: []),
    "_cloud_runtime_client_id": lambda key: "offline-test-runtime",
    "_build_default_client_state": lambda: {},
    "_cloud_token_fingerprint": lambda token: "offline-fingerprint",
    "_cloud_account_id_for_state": lambda state: "offline-demo-account",
    "_cloud_identity_for_state": lambda state: {"identity_type": "token_fingerprint"},
    "_current_session_user_safe": lambda: "offline-test-user",
    "DERIV_ACCOUNT_ID": "",
    "DERIV_APP_ID": "legacy-placeholder-app",
    "CloudProfileStrategy": lambda: object(),
    "_start_ws_worker_thread": lambda cid, state, reason: workers.append({"mode": state["api_token_type"], "reason": reason}),
    "time": SimpleNamespace(time=lambda: 0),
    "logger": SimpleNamespace(info=lambda *args: None, exception=lambda *args: None),
}
ensure_cloud = load_function("_ensure_cloud_runtime_for_state", namespace)
ensure_cloud({"username": "offline-test-user", "api_token": "placeholder-not-a-token", "api_token_type": "pat", "options_account_id": "offline-demo-account", "pat_options_account_id": "offline-demo-account", "deriv_app_id": "pat-placeholder-app"}, "user:offline-test-user:token:offline", {"current_market": "R_10", "running": True})
cloud = {
    "case": "cloud_pat_mode_copy",
    "network_calls": 0,
    "source_mode": "pat",
    "actual_worker_mode": workers[0]["mode"],
    "bug_reproduced": workers[0]["mode"] != "pat",
}
results = [human, cloud]
assert all(result["bug_reproduced"] for result in results), "An observed defect changed; re-check the report."
(Path(__file__).parent / "offline-reproductions.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results))
