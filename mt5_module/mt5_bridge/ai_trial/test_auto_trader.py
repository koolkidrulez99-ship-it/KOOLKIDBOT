from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


class AutoTraderSafetyTests(unittest.TestCase):
    def test_same_completed_candle_signal_is_never_submitted_twice(self):
        # Import through the real bridge module so this exercises the persisted
        # per-workspace signal registry used by both manual and automatic execution.
        import hub_auth
        from mt5_module.mt5_bridge import main
        import store
        from ai_trial import storage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_data_dir, old_trial_root = store.DATA_DIR, storage.ROOT
            store.DATA_DIR = root / "bridge-data"
            storage.ROOT = root / "bridge"
            token = hub_auth.set_workspace("ws_test_ai")
            try:
                snapshot = {
                    "account_login": 1001,
                    "symbol": "XAUUSD",
                    "decision": "BUY",
                    "proposed_trade": {
                        "direction": "BUY",
                        "time": 123456,
                        "entry": 2000.0,
                        "sl": 1990.0,
                        "tp": 2030.0,
                    },
                }
                config = {"enabled": True, "account_login": 1001, "symbol": "XAUUSD"}
                store.update_state(lambda state: state.update(ai_auto_config=config))
                with patch.object(main, "_connected_ai_account", return_value={"login": 1001, "account_type": "demo", "status": "connected"}), patch.object(main, "_run_ai_trial_scan", return_value=snapshot), patch.object(main, "trade", return_value={"retcode": 10009, "ticket": 42}):
                    first = main._execute_apostle_snapshot(snapshot, 0.01, source="ai_auto_human_apostle", expected_config=config)
                    self.assertTrue(first["executed"])
                    self.assertTrue(first["automatic"])
                    with self.assertRaises(HTTPException) as ctx:
                        main._execute_apostle_snapshot(snapshot, 0.01, source="ai_auto_human_apostle")
                    self.assertEqual(ctx.exception.status_code, 409)
                    self.assertIn("already submitted", str(ctx.exception.detail).lower())
            finally:
                hub_auth.reset_workspace(token)
                store.DATA_DIR, storage.ROOT = old_data_dir, old_trial_root


if __name__ == "__main__":
    unittest.main()
