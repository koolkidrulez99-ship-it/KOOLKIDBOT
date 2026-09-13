"""KOOLKID MT5 Hub Flask mount.

This file intentionally contains only web-serving glue. It does not import or
modify the existing Deriv trading engine. Build mt5_bot/ first so mt5_bot/dist
exists, then register this Blueprint from the main Flask app.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from flask import Blueprint, redirect, send_file, send_from_directory, url_for

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "mt5_bot" / "dist"


def create_mt5_blueprint(
    login_required: Callable[[], bool],
    is_admin: Callable[[], bool] | None = None,
    login_endpoint: str = "login",
    admin_endpoint: str = "admin_panel",
) -> Blueprint:
    bp = Blueprint("mt5_hub", __name__)

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
