"""Read-only client for the existing MT5 bridge. It never imports or controls MT5."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from flask import current_app, has_request_context, session


class Mt5ReadProvider:
    def __init__(self):
        self.base = os.getenv("AI_INTELLIGENCE_MT5_URL", "http://127.0.0.1:8000").rstrip("/")
        self.timeout = float(os.getenv("AI_INTELLIGENCE_MT5_TIMEOUT", "8"))

    def _user_token(self):
        if not has_request_context() or not session.get("user"):
            raise RuntimeError("Sign in before requesting MT5 account data.")
        username = str(session["user"])
        configured = current_app.config.get("AI_INTELLIGENCE_MT5_USER_TOKENS")
        if configured is None:
            try:
                configured = json.loads(os.getenv("AI_INTELLIGENCE_MT5_USER_TOKENS", "{}"))
            except ValueError:
                raise RuntimeError("MT5 user mapping is not configured correctly.") from None
        token = configured.get(username) if isinstance(configured, dict) else None
        # The old single token is allowed only with an explicitly named owner.
        if not token and username == os.getenv("AI_INTELLIGENCE_MT5_USER", ""):
            token = os.getenv("AI_INTELLIGENCE_MT5_TOKEN", "")
        if not isinstance(token, str) or not token:
            raise RuntimeError("This KOOLKID user has no linked MT5 workspace. Use AI Intelligence inside the MT5 Hub.")
        return token

    def get(self, path, params=None):
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base}{path}{'?' + query if query else ''}"
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._user_token()}"}
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
