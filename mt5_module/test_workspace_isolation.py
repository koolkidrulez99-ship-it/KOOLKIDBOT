"""Small no-MT5 regression check for MT5 Hub workspace isolation."""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("MT5_HUB_AUTH_SECRET", "targeted-test-secret")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mt5_module" / "mt5_bridge"))
sys.path.insert(0, str(ROOT))

# The bridge's existing upload route registers only when python-multipart is
# present. This state-only test never exercises uploads, so avoid a dependency
# install just to import that route table.
multipart = types.ModuleType("multipart")
multipart.__version__ = "0.0"
multipart_submodule = types.ModuleType("multipart.multipart")
multipart_submodule.parse_options_header = lambda value: (value, {})
sys.modules.setdefault("multipart", multipart)
sys.modules.setdefault("multipart.multipart", multipart_submodule)

import main as bridge  # noqa: E402
import store as bridge_store  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from hub_auth import reset_workspace, set_workspace, verify_token  # noqa: E402
from mt5_module.mt5_multi_account import app as multi  # noqa: E402
from mt5_module.mt5_multi_account.models import ConnectRequest  # noqa: E402


def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_users, original_data, original_base = bridge.HUB_USERS_FILE, bridge_store.DATA_DIR, multi.BASE
        try:
            bridge.HUB_USERS_FILE = root / "users.json"
            bridge_store.DATA_DIR = root / "bridge"
            multi.BASE = root / "multi"
            multi._RUNTIMES.clear()

            user_a = bridge.hub_signup(bridge.HubAuthPayload(username="user_a", password="password-a"))
            user_b = bridge.hub_signup(bridge.HubAuthPayload(username="user_b", password="password-b"))
            assert verify_token(user_a["token"])["workspace_id"] == user_a["workspace_id"]
            assert user_a["workspace_id"] != user_b["workspace_id"]

            token = set_workspace(user_a["workspace_id"])
            try:
                bridge_store.upsert_profile({"login": 12345, "nickname": "A", "server": "demo"})
                state = multi.STATE.load()
                state["accounts"] = {f"a{i}": {"account_id": f"a{i}", "login": 1000 + i, "mode": "real"} for i in range(10)}
                state["copy_config"] = {"master_account_id": "a0", "slave_account_ids": ["a1"], "poll_ms": 300}
                state["copy_enabled"] = True
                state["ai_settings"] = {"auto_trading": True}
                multi.STATE.save(state)
                try:
                    multi.connect(ConnectRequest(account_id="a10", login=1010, password="unused"))
                    raise AssertionError("11th account was accepted")
                except HTTPException as exc:
                    assert "10 MT5 accounts per workspace" in str(exc.detail)
            finally:
                reset_workspace(token)

            token = set_workspace(user_b["workspace_id"])
            try:
                assert bridge_store.read_state()["profiles"] == []
                assert multi.STATE.load()["accounts"] == {}
                # A manually supplied account id from User A resolves only inside User B's scoped pool.
                assert not multi.POOL.status("a0")["connected"]
                b_state = multi.STATE.load()
                b_state["accounts"]["a0"] = {"account_id": "a0", "login": 1000, "mode": "real"}
                multi.STATE.save(b_state)
                assert multi._runtime().pool._key("a0") != f"{user_a['workspace_id']}--a0"
            finally:
                reset_workspace(token)

            token = set_workspace(user_a["workspace_id"])
            try:
                # Browser logout changes no server state: persisted Copy/AI flags remain.
                persisted = multi.STATE.load()
                assert persisted["copy_enabled"] is True
                assert persisted["ai_settings"]["auto_trading"] is True
                multi._RUNTIMES.pop(user_a["workspace_id"], None)
                restored = multi._runtime()
                assert restored.state.load()["copy_enabled"] is True
                assert restored.copy.config["master_account_id"] == "a0"
            finally:
                reset_workspace(token)
        finally:
            bridge.HUB_USERS_FILE, bridge_store.DATA_DIR, multi.BASE = original_users, original_data, original_base
            multi._RUNTIMES.clear()


if __name__ == "__main__":
    run()
    print("workspace isolation checks passed")
