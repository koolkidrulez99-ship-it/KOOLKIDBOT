web: gunicorn server:app --worker-class gthread --workers 1 --threads 8 --bind 0.0.0.0:$PORT --timeout 120 --graceful-timeout 30
