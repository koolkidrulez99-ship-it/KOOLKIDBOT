"""KOOLKID MT5 Hub Flask mount.

This file intentionally contains only web-serving glue. It does not import or
modify the existing Deriv trading engine. Build mt5_bot/ first so mt5_bot/dist
exists, then register this Blueprint from the main Flask app.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, Response, request, redirect, send_file, send_from_directory, url_for

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "mt5_bot" / "dist"


def _proxy_mt5_request(upstream_base: str, upstream_path: str) -> Response:
    # Browser private-network/CORS preflights must terminate on the local
    # Flask proxy. Forwarding OPTIONS into an older MT5 worker can return
    # 400 before the browser is allowed to use the fast local route.
    if request.method == "OPTIONS":
        return Response(status=204)
    query = request.query_string.decode("utf-8")
    url = f"{upstream_base.rstrip('/')}/{upstream_path}"
    if query:
        url = f"{url}?{query}"
    headers = {
        name: value for name in ("Authorization", "Content-Type", "Accept", "Origin", "Access-Control-Request-Method", "Access-Control-Request-Headers")
        if (value := request.headers.get(name))
    }
    data = request.get_data() if request.method in {"POST", "PUT", "PATCH", "DELETE"} else None
    try:
        with urlopen(Request(url, data=data, method=request.method, headers=headers), timeout=90) as upstream:
            response_headers = {name: value for name, value in upstream.headers.items() if name.lower() not in {"content-length", "connection", "transfer-encoding"}}
            return Response(upstream.read(), status=upstream.status, headers=response_headers)
    except HTTPError as exc:
        return Response(exc.read(), status=exc.code, content_type=exc.headers.get_content_type() if exc.headers else "application/json")
    except URLError:
        return Response(json.dumps({"detail": "MT5 service is offline."}), status=503, content_type="application/json")


def create_mt5_blueprint(
    login_required: Callable[[], bool],
    is_admin: Callable[[], bool] | None = None,
    login_endpoint: str = "login",
    admin_endpoint: str = "admin_panel",
) -> Blueprint:
    bp = Blueprint("mt5_hub", __name__)
    bridge_url = os.getenv("MT5_BRIDGE_PROXY_URL", "http://127.0.0.1:8003")
    multi_url = os.getenv("MT5_MULTI_PROXY_URL", "http://127.0.0.1:8002")
    local_browser_origins = {
        "https://koolkidbot.org",
        "https://www.koolkidbot.org",
        "http://127.0.0.1:5055",
        "http://localhost:5055",
    }

    @bp.after_request
    def allow_local_mt5_browser_proxy(response: Response):
        origin = str(request.headers.get("Origin") or "")
        if origin in local_browser_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = request.headers.get(
                "Access-Control-Request-Headers", "Authorization, Content-Type, Accept"
            )
            if str(request.headers.get("Access-Control-Request-Private-Network") or "").lower() == "true":
                response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

    @bp.route("/mt5-api", defaults={"upstream_path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @bp.route("/mt5-api/<path:upstream_path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def mt5_bridge_proxy(upstream_path: str):
        return _proxy_mt5_request(bridge_url, upstream_path)

    @bp.route("/mt5-multi", defaults={"upstream_path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    @bp.route("/mt5-multi/<path:upstream_path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def mt5_multi_proxy(upstream_path: str):
        return _proxy_mt5_request(multi_url, upstream_path)

    @bp.route("/mt5-bot", defaults={"asset_path": ""}, strict_slashes=False)
    @bp.route("/mt5-bot/<path:asset_path>")
    def mt5_bot_page(asset_path: str):
        if not login_required():
            return redirect(url_for(login_endpoint))
        if is_admin is not None and is_admin():
            return redirect(url_for(admin_endpoint))

        index_file = DIST_DIR / "index.html"
        if not index_file.exists():
            return (
                "MT5 Hub frontend is not built. Run npm ci && npm run build inside mt5_bot/.",
                503,
            )

        if asset_path:
            candidate = (DIST_DIR / asset_path).resolve()
            try:
                candidate.relative_to(DIST_DIR.resolve())
            except ValueError:
                candidate = index_file
            if candidate.is_file():
                return send_from_directory(DIST_DIR, asset_path)

        # React BrowserRouter fallback for /mt5-bot/mt5/... routes.
        return send_file(index_file)

    return bp
