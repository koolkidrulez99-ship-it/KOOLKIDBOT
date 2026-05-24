from __future__ import annotations

from flask import jsonify, request, session


def _parse_settings_payload(data: dict | None) -> dict:
    raw = data or {}
    allowed = raw.get("allowed_markets")
    if isinstance(allowed, str):
        allowed = [item.strip() for item in allowed.replace("\n", ",").replace(";", ",").split(",") if item.strip()]
    settings = {}
    for key in (
        "base_stake",
        "take_profit_target",
        "max_reinvest_steps",
        "capital_build_mode",
        "market_switch_minutes",
        "allowed_markets",
        "duration",
        "duration_unit",
        "enable_telegram_alerts",
        "enable_whatsapp_alerts",
        "allow_auto_resume",
        "cooldown_seconds",
        "max_daily_loss",
        "max_trades_per_session",
        "low_balance_stop",
        "specific_time_enabled",
        "specific_trade_times",
        "specific_time_window_minutes",
        "max_digit9_last10",
        "max_digit9_last20",
        "max_digit9_last5",
        "min_seconds_between_99_streaks",
        "telegram_bot_token",
        "telegram_chat_id",
        "whatsapp_webhook_url",
    ):
        if key == "allowed_markets":
            value = allowed
        else:
            value = raw.get(key)
        if value not in (None, ""):
            settings[key] = value
    return settings


def register_cloud_routes(
    app,
    *,
    cloud_manager,
    login_required,
    get_client_state,
    ensure_tick_subscription,
    socketio=None,
    get_cloud_identity=None,
    ensure_cloud_runtime=None,
    stop_cloud_runtime=None,
    can_use_cloud_profile=None,
):
    def _current_user():
        return str(session.get("user") or "").strip().lower()

    def _identity(require_token=False):
        cid, state = get_client_state()
        if callable(get_cloud_identity):
            info = get_cloud_identity(state, require_token=require_token) or {}
            info.setdefault("client_id", cid)
            info.setdefault("state", state)
            return info
        key = _current_user()
        return {"client_id": cid, "state": state, "key": key, "token_verified": False}

    def _token_required_response():
        return jsonify({
            "status": "error",
            "message": "Connect and verify the exact Deriv API token or Deriv account before starting or saving Cloud Trading.",
            "requires_token_verification": True,
        }), 400

    def _attach_identity(status, ident):
        status = dict(status or {})
        status["token_verified"] = bool((ident or {}).get("token_verified"))
        status["requires_token_verification"] = not bool((ident or {}).get("token_verified"))
        if (ident or {}).get("cloud_account_id"):
            status["cloud_account_id"] = ident.get("cloud_account_id")
        if (ident or {}).get("connection_mode"):
            status["connection_mode"] = ident.get("connection_mode")
        if (ident or {}).get("identity_type"):
            status["cloud_identity_type"] = ident.get("identity_type")
        if (ident or {}).get("token_fingerprint"):
            status["token_fingerprint"] = ident.get("token_fingerprint")
        return status

    def _cloud_allowed():
        return True if not callable(can_use_cloud_profile) else bool(can_use_cloud_profile())

    def _cloud_forbidden_response():
        return jsonify({
            "status": "error",
            "message": "Cloud Trading is available for lifetime users only.",
        }), 403

    @app.route("/cloud/under9/start", methods=["POST"])
    def cloud_under9_start():
        if not login_required():
            return jsonify({"error": "Unauthorized"}), 403
        if not _cloud_allowed():
            return _cloud_forbidden_response()
        ident = _identity(require_token=True)
        cid = ident.get("client_id")
        state = ident.get("state") or {}
        username = ident.get("key") or ""
        if not username:
            return _token_required_response()
        settings = _parse_settings_payload(request.json or {})
        status = cloud_manager.start(username, cid, settings)
        if callable(ensure_cloud_runtime):
            ensure_cloud_runtime(state, username, status)
        else:
            ensure_tick_subscription(state, status.get("current_market"), force=False, reason="cloud_under9_start", client_id=cid)
        status = _attach_identity(status, ident)
        if socketio:
            socketio.emit("cloud_under9_status", status, room=cid)
        return jsonify(status)

    @app.route("/cloud/under9/restart", methods=["POST"])
    def cloud_under9_restart():
        if not login_required():
            return jsonify({"error": "Unauthorized"}), 403
        if not _cloud_allowed():
            return _cloud_forbidden_response()
        ident = _identity(require_token=True)
        cid = ident.get("client_id")
        state = ident.get("state") or {}
        username = ident.get("key") or ""
        if not username:
            return _token_required_response()
        if hasattr(cloud_manager, "has_session") and not cloud_manager.has_session(username):
            return jsonify({
                "status": "error",
                "message": "No saved Cloud session was found for this verified token/account. Start Cloud Bot first.",
            }), 404
        status = cloud_manager.start(username, cid, None)
        if callable(ensure_cloud_runtime):
            ensure_cloud_runtime(state, username, status)
        else:
            ensure_tick_subscription(state, status.get("current_market"), force=False, reason="cloud_under9_restart", client_id=cid)
        status["manual_restart"] = True
        status = _attach_identity(status, ident)
        if socketio:
            socketio.emit("cloud_under9_status", status, room=cid)
        return jsonify(status)

    @app.route("/cloud/under9/stop", methods=["POST"])
    def cloud_under9_stop():
        if not login_required():
            return jsonify({"error": "Unauthorized"}), 403
        if not _cloud_allowed():
            return _cloud_forbidden_response()
        ident = _identity(require_token=False)
        cid = ident.get("client_id")
        username = ident.get("key") or _current_user()
        status = cloud_manager.stop(username, "Stopped")
        if callable(stop_cloud_runtime):
            stop_cloud_runtime(username, "cloud_under9_stop")
        status = _attach_identity(status, ident)
        if socketio:
            socketio.emit("cloud_under9_status", status, room=cid)
        return jsonify(status)

    @app.route("/cloud/under9/status", methods=["GET"])
    def cloud_under9_status():
        if not login_required():
            return jsonify({"error": "Unauthorized"}), 403
        if not _cloud_allowed():
            return _cloud_forbidden_response()
        ident = _identity(require_token=False)
        username = ident.get("key") or ""
        if not username:
            return jsonify({
                "status": "success",
                "cloud_enabled": False,
                "running": False,
                "cloud_status": "Connect the exact Deriv API token/account to verify this Cloud session.",
                "requires_token_verification": True,
                "token_verified": False,
                "settings": {},
                "allowed_markets": [],
                "current_market": "",
                "current_stake": 0,
                "session_profit": 0,
                "reinvest_step": 0,
                "wins": 0,
                "losses": 0,
            })
        status = cloud_manager.status(username)
        status = _attach_identity(status, ident)
        return jsonify(status)

    @app.route("/cloud/under9/history", methods=["GET"])
    def cloud_under9_history():
        if not login_required():
            return jsonify({"error": "Unauthorized"}), 403
        if not _cloud_allowed():
            return _cloud_forbidden_response()
        ident = _identity(require_token=False)
        username = ident.get("key") or ""
        return jsonify({"status": "success", "history": cloud_manager.history(username) if username else []})

    @app.route("/cloud/under9/settings", methods=["POST"])
    def cloud_under9_settings():
        if not login_required():
            return jsonify({"error": "Unauthorized"}), 403
        if not _cloud_allowed():
            return _cloud_forbidden_response()
        ident = _identity(require_token=True)
        cid = ident.get("client_id")
        state = ident.get("state") or {}
        username = ident.get("key") or ""
        if not username:
            return _token_required_response()
        settings = _parse_settings_payload(request.json or {})
        status = cloud_manager.update_settings(username, settings)
        if status.get("running"):
            if callable(ensure_cloud_runtime):
                ensure_cloud_runtime(state, username, status)
            else:
                ensure_tick_subscription(state, status.get("current_market"), force=False, reason="cloud_under9_settings", client_id=cid)
        status = _attach_identity(status, ident)
        if socketio:
            socketio.emit("cloud_under9_status", status, room=cid)
        return jsonify(status)
