"""Read-only client for the existing MT5 bridge. It never imports or controls MT5."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


class Mt5ReadProvider:
    def __init__(self):
        self.base = os.getenv("AI_INTELLIGENCE_MT5_URL", "http://127.0.0.1:8000").rstrip("/")
        self.token = os.getenv("AI_INTELLIGENCE_MT5_TOKEN", "")
        self.timeout = float(os.getenv("AI_INTELLIGENCE_MT5_TIMEOUT", "8"))

    def get(self, path, params=None):
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base}{path}{'?' + query if query else ''}"
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read(2_000_000).decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("Existing MT5 data service is unavailable.") from exc

    def candles(self, account, symbol, timeframe, count=300):
        return self.get(f"/api/mt5/candles/{urllib.parse.quote(symbol, safe='')}", {"timeframe": timeframe, "count": max(20, min(int(count), 1000)), "account_login": account})

    def accounts(self):
        return self.get("/api/mt5/accounts")

    def symbols(self, account):
        return self.get("/api/mt5/symbols", {"account_login": account, "visible_only": "true", "limit": 1000})

    def positions(self):
        return self.get("/api/mt5/positions")
