from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mt5_module"))
sys.path.insert(0, str(ROOT / "mt5_module" / "mt5_bridge"))

import ea_worker_client  # noqa: E402
import main  # noqa: E402
import multi_account_client  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_public_worker_health_does_not_need_workspace_context():
    with patch.object(ea_worker_client, "urlopen", return_value=FakeResponse({"ok": True, "service": "mt5-ea-worker"})):
        assert ea_worker_client.public_status()["status"] == "online"
    with patch.object(multi_account_client, "urlopen", return_value=FakeResponse({"ok": True, "service": "mt5-multi-account-worker"})):
        assert multi_account_client.public_status()["status"] == "online"


def test_bridge_public_health_uses_workspace_neutral_checks():
    account = {"status": "online", "ok": True, "service": "mt5-multi-account-worker"}
    ea = {"status": "online", "ok": True, "service": "mt5-ea-worker"}
    with patch.object(main.multi_account_client, "public_status", return_value=account), patch.object(main.ea_worker_client, "public_status", return_value=ea):
        result = main.health()
    assert result["ok"] is True
    assert result["copy_worker"] == "online"
    assert result["account_worker"] == account
    assert result["ea_worker"] == ea
