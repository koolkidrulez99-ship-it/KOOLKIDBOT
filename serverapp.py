from server import app, socketio

# Gunicorn accepts `serverapp` and defaults to `application` when no callable
# name is given, so keep both names available for deploy compatibility.
application = app

