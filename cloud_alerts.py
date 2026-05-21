from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


class CloudAlertDispatcher:
    def __init__(self, logger=None):
        self.logger = logger

    def _log(self, level, message, *args):
        if self.logger and hasattr(self.logger, level):
            getattr(self.logger, level)(message, *args)

    def send(self, event: str, message: str, settings: dict | None = None):
        cfg = settings or {}
        if cfg.get("enable_telegram_alerts"):
            self._send_telegram(message, cfg)
        if cfg.get("enable_whatsapp_alerts"):
            self._send_whatsapp_placeholder(event, message, cfg)

    def _send_telegram(self, message: str, settings: dict):
        token = str(settings.get("telegram_bot_token") or os.getenv("CLOUD_TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = str(settings.get("telegram_chat_id") or os.getenv("CLOUD_TELEGRAM_CHAT_ID") or "").strip()
        if not token or not chat_id:
            self._log("info", "cloud_alert telegram skipped: missing token/chat id")
            return
        url = f"https://api.telegram.org/bot{urllib.parse.quote(token)}/sendMessage"
        payload = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=payload, method="POST")
            urllib.request.urlopen(req, timeout=8).read()
        except Exception as exc:
            self._log("warning", "cloud_alert telegram failed: %s", exc)

    def _send_whatsapp_placeholder(self, event: str, message: str, settings: dict):
        provider_url = str(settings.get("whatsapp_webhook_url") or os.getenv("CLOUD_WHATSAPP_WEBHOOK_URL") or "").strip()
        if not provider_url:
            self._log("info", "cloud_alert whatsapp placeholder event=%s message=%s", event, message)
            return
        try:
            body = json.dumps({"event": event, "message": message}).encode("utf-8")
            req = urllib.request.Request(provider_url, data=body, method="POST", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=8).read()
        except Exception as exc:
            self._log("warning", "cloud_alert whatsapp failed: %s", exc)
