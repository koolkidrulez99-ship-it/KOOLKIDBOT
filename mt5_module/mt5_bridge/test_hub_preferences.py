from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mt5_module"))
sys.path.insert(0, str(ROOT / "mt5_module" / "mt5_bridge"))

import main  # noqa: E402


def test_market_preferences_are_saved_per_workspace_state(monkeypatch):
    state = {"hub_preferences": {
        "pollMs": 5000,
        "confirmDanger": True,
        "restoreWorkspace": True,
        "reconnectOnStartup": True,
        "marketBrokerFilter": "all",
        "marketCategoryFilter": "all",
        "customBrokerFamilies": ["deriv", "weltrade", "other"],
        "customMarketGroups": ["synthetic", "forex", "metals", "indices", "crypto", "stocks", "energies", "weltrade_syntx"],
        "marketFavorites": {},
    }}

    monkeypatch.setattr(main, "read_state", lambda: state)
    monkeypatch.setattr(main, "update_state", lambda mutator: mutator(state))

    saved = main.save_hub_preferences({
        "marketBrokerFilter": "weltrade",
        "marketCategoryFilter": "fxvol",
        "customBrokerFamilies": ["weltrade"],
        "customMarketGroups": ["weltrade_syntx"],
        "marketFavorites": {"77123": ["FXV20", "SFXV40"]},
    })

    assert saved["marketBrokerFilter"] == "weltrade"
    assert saved["marketCategoryFilter"] == "fxvol"
    assert saved["marketFavorites"]["77123"] == ["FXV20", "SFXV40"]
    assert main.get_hub_preferences()["marketBrokerFilter"] == "weltrade"


def test_invalid_market_preferences_are_sanitized(monkeypatch):
    state = {"hub_preferences": {}}
    monkeypatch.setattr(main, "update_state", lambda mutator: mutator(state))

    saved = main.save_hub_preferences({
        "marketBrokerFilter": "made-up",
        "marketCategoryFilter": "made-up",
        "customBrokerFamilies": ["weltrade", "bad"],
        "customMarketGroups": ["forex", "bad"],
    })

    assert saved["marketBrokerFilter"] == "all"
    assert saved["marketCategoryFilter"] == "all"
    assert saved["customBrokerFamilies"] == ["weltrade"]
    assert saved["customMarketGroups"] == ["forex"]
