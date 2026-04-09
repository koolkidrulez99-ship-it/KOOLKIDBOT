import os


def _should_enable_eventlet():
    configured = str(os.environ.get("SOCKETIO_ASYNC_MODE") or "").strip().lower()
    if configured:
        return configured == "eventlet"
    return any(
        str(os.environ.get(name) or "").strip()
        for name in (
            "RENDER",
            "RENDER_SERVICE_ID",
            "RENDER_EXTERNAL_HOSTNAME",
            "RENDER_INSTANCE_ID",
        )
    )


if _should_enable_eventlet():
    os.environ.setdefault("EVENTLET_NO_GREENDNS", "yes")
    try:
        import eventlet

        eventlet.monkey_patch()
    except Exception:
        pass


from server import app  # noqa: E402


# Keep the deploy entrypoint explicit for Gunicorn/Render.
application = app
