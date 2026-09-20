from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .config_builder import build_config
from .ea_observer import capture_log_offsets, inspect_ea_logs
from .ea_manager import install_files
from .models import StartBotRequest
from . import worker
from .main import require_worker_token
from hub_auth import reset_workspace, set_workspace
from fastapi import HTTPException


class ConfigTests(unittest.TestCase):
    def test_builds_supported_startup_config(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "startup.ini"
            build_config(path, login=123, server="Broker-Demo", expert=r"KOOLKID\7\Demo", preset="demo.set", symbol="EURUSD", timeframe="M15", allow_trading=True, allow_dll=False)
            text = path.read_text(encoding="utf-8")
            self.assertIn("Expert=KOOLKID\\7\\Demo", text)
            self.assertIn("Server=Broker-Demo", text)
            self.assertIn("ExpertParameters=demo.set", text)
            self.assertIn("Symbol=EURUSD", text)
            self.assertIn("Period=M15", text)
            self.assertIn("AllowDllImport=0", text)

    def test_rejects_invalid_timeframe(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "Unsupported MT5 timeframe"):
                build_config(Path(temp) / "x.ini", login=1, expert="X", preset=None, symbol="EURUSD", timeframe="BAD", allow_trading=True, allow_dll=False)

    def test_missing_ea_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "was not found"):
                install_files(Path(temp) / "data", 1, Path(temp) / "missing.ex5", None)

    def test_observer_uses_only_fresh_ea_log_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            log_dir = data / "MQL5" / "Logs"
            log_dir.mkdir(parents=True)
            log = log_dir / "20260914.log"
            log.write_bytes("OLD DEAR_BRUCE_PREMIUM initialization failed\n".encode("utf-16-le"))
            offsets = capture_log_offsets(data)
            with log.open("ab") as handle:
                handle.write("DEAR_BRUCE_PREMIUM (USDCAD,M15) Initialized: M5 execution / H4 bias. Trendline break.\n".encode("utf-16-le"))
            result = inspect_ea_logs(data, "DEAR_BRUCE_PREMIUM.ex5", offsets=offsets)
            self.assertTrue(result["ea_verified"])
            self.assertEqual(result["observed_timeframes"], ["H4", "M15", "M5"])
            self.assertIn("Trendline logic", result["observed_traits"])
            self.assertIn("Higher-timeframe bias", result["observed_traits"])


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self._workspace_token = set_workspace("worker-checks")

    def tearDown(self):
        reset_workspace(self._workspace_token)

    def request(self, ea: Path, terminal: Path) -> StartBotRequest:
        return StartBotRequest(bot_id=7, account_login=123, account_type="demo", symbol="EURUSD", timeframe="M15", ea_path=str(ea), ea_filename=ea.name, terminal_path=str(terminal))

    def test_start_uses_config_command_and_handles_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ea = root / "library" / "Demo.ex5"
            ea.parent.mkdir()
            ea.write_bytes(b"compiled-ea")
            terminal = root / "terminal64.exe"
            terminal.write_bytes(b"terminal")
            data = root / "data"
            captured = {}
            state = {"assignments": []}

            class FakeProcess:
                pid = 4242
                returncode = None
                def poll(self): return None

            def fake_popen(args, **kwargs):
                captured["args"] = args
                return FakeProcess()

            def fake_write(next_state):
                state.clear(); state.update(next_state)

            with patch.dict(os.environ, {"MT5_EA_LIBRARY_ROOT": str(ea.parent)}), \
                 patch.object(worker, "select_terminal", return_value=terminal), \
                 patch.object(worker, "terminal_data_dir", return_value=data), \
                 patch.object(worker, "prepare_dedicated_terminal", return_value=(terminal, data)), \
                 patch.object(worker, "read_state", side_effect=lambda: {"assignments": [dict(x) for x in state["assignments"]]}), \
                 patch.object(worker, "write_state", side_effect=fake_write), \
                 patch.object(worker.subprocess, "Popen", side_effect=fake_popen), \
                 patch.object(worker.time, "sleep"), \
                 patch.object(worker, "capture_log_offsets", return_value={}), \
                 patch.object(worker, "inspect_ea_logs", return_value={"ea_verified": True, "verification_error": None, "observed_messages": [], "observed_timeframes": [], "observed_traits": [], "last_ea_activity": None}), \
                 patch.object(worker, "_terminal_metrics", return_value={"account_verified": True, "open_positions": 0, "current_pl": 0, "today_pl": 0}), \
                 patch.object(worker, "reconcile", side_effect=lambda: [dict(x) for x in state["assignments"]]):
                first = worker.start_bot(self.request(ea, terminal))
                second = worker.start_bot(self.request(ea, terminal))

            self.assertEqual(first["status"], "running")
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(captured["args"][0], str(terminal))
            self.assertEqual(captured["args"][1], "/portable")
            self.assertTrue(captured["args"][2].startswith("/config:"))
            self.assertTrue((data / "MQL5" / "Experts" / "KOOLKID" / "7" / "Demo.ex5").is_file())

    def test_same_bot_can_run_distinct_market_instances(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ea = root / "library" / "Demo.ex5"
            ea.parent.mkdir()
            ea.write_bytes(b"compiled-ea")
            terminal = root / "terminal64.exe"
            terminal.write_bytes(b"terminal")
            data = root / "data"
            state = {"assignments": []}
            next_pid = {"value": 5000}

            class FakeProcess:
                returncode = None
                def __init__(self, pid): self.pid = pid
                def poll(self): return None

            def fake_popen(args, **kwargs):
                next_pid["value"] += 1
                return FakeProcess(next_pid["value"])

            def fake_write(next_state):
                state.clear(); state.update(next_state)

            def fake_prepare(source, source_data, terminal_id):
                isolated = root / "workers" / terminal_id / "terminal64.exe"
                isolated.parent.mkdir(parents=True, exist_ok=True)
                isolated.write_bytes(b"terminal")
                return isolated, isolated.parent

            with patch.dict(os.environ, {"MT5_EA_LIBRARY_ROOT": str(ea.parent)}), \
                 patch.object(worker, "select_terminal", return_value=terminal), \
                 patch.object(worker, "terminal_data_dir", return_value=data), \
                 patch.object(worker, "prepare_dedicated_terminal", side_effect=fake_prepare), \
                 patch.object(worker, "read_state", side_effect=lambda: {"assignments": [dict(x) for x in state["assignments"]]}), \
                 patch.object(worker, "write_state", side_effect=fake_write), \
                 patch.object(worker.subprocess, "Popen", side_effect=fake_popen), \
                 patch.object(worker.time, "sleep"), \
                 patch.object(worker, "capture_log_offsets", return_value={}), \
                 patch.object(worker, "inspect_ea_logs", return_value={"ea_verified": True, "verification_error": None, "observed_messages": [], "observed_timeframes": [], "observed_traits": [], "last_ea_activity": None}), \
                 patch.object(worker, "_terminal_metrics", return_value={"account_verified": True, "open_positions": 0, "current_pl": 0, "today_pl": 0}), \
                 patch.object(worker, "reconcile", side_effect=lambda: [dict(x) for x in state["assignments"]]):
                first = worker.start_bot(self.request(ea, terminal).model_copy(update={"instance_key": "market-1", "symbol": "EURUSD"}))
                second = worker.start_bot(self.request(ea, terminal).model_copy(update={"instance_key": "market-2", "symbol": "GBPUSD"}))

            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual({row["instance_key"] for row in state["assignments"]}, {"market-1", "market-2"})
            self.assertEqual({row["symbol"] for row in state["assignments"]}, {"EURUSD", "GBPUSD"})

    def test_live_start_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ea = root / "Demo.ex5"; ea.write_bytes(b"ea")
            terminal = root / "terminal64.exe"; terminal.write_bytes(b"terminal")
            request = self.request(ea, terminal).model_copy(update={"account_type": "live", "allow_live": False})
            with patch.object(worker, "reconcile", return_value=[]):
                with self.assertRaisesRegex(ValueError, "explicit confirmation"):
                    worker.start_bot(request)

    def test_worker_token_is_enforced_when_configured(self):
        with patch.dict(os.environ, {"MT5_WORKER_API_TOKEN": "test-secret"}):
            with self.assertRaises(HTTPException):
                require_worker_token(None)
            self.assertIsNone(require_worker_token("Bearer test-secret"))

    def test_bridge_terminal_is_cloned_to_dedicated_instance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ea = root / "library" / "Demo.ex5"; ea.parent.mkdir(); ea.write_bytes(b"ea")
            terminal = root / "bridge" / "terminal64.exe"; terminal.parent.mkdir(); terminal.write_bytes(b"terminal")
            data = root / "bridge-data"; data.mkdir()
            isolated = root / "worker" / "terminal64.exe"; isolated.parent.mkdir(); isolated.write_bytes(b"terminal")
            isolated_data = isolated.parent
            request = self.request(ea, terminal).model_copy(update={"bridge_terminal_path": str(terminal.parent), "bridge_data_path": str(data)})
            captured = {}
            class FakeProcess:
                pid = 8181
                returncode = None
                def poll(self): return None
            def fake_popen(args, **kwargs):
                captured["args"] = args
                return FakeProcess()
            with patch.dict(os.environ, {"MT5_EA_LIBRARY_ROOT": str(ea.parent)}), \
                 patch.object(worker, "reconcile", return_value=[]), \
                 patch.object(worker, "prepare_dedicated_terminal", return_value=(isolated, isolated_data)) as prepare, \
                 patch.object(worker.subprocess, "Popen", side_effect=fake_popen), \
                 patch.object(worker.time, "sleep"), patch.object(worker, "capture_log_offsets", return_value={}), \
                 patch.object(worker, "inspect_ea_logs", return_value={"ea_verified": True, "verification_error": None, "observed_messages": [], "observed_timeframes": [], "observed_traits": [], "last_ea_activity": None}), \
                 patch.object(worker, "_terminal_metrics", return_value={"account_verified": True}), \
                 patch.object(worker, "read_state", return_value={"assignments": []}), patch.object(worker, "write_state"):
                result = worker.start_bot(request)
            prepare.assert_called_once()
            self.assertEqual(result["terminal_path"], str(isolated))
            self.assertNotEqual(Path(result["terminal_path"]).parent, terminal.parent)


if __name__ == "__main__":
    unittest.main()
