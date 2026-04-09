from server import app, socketio

# Flask-SocketIO is attached to the Flask app inside server.py, so Gunicorn
# should import the Flask application object from this small deploy entrypoint.
# Keeping both names avoids platform/runtime ambiguity during deploys.
application = app
