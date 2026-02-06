# timeout 300: textbook PDF ingest can take 1–3 min.
# workers 1, threads 100: Flask-SocketIO requires the default sync worker
# (not gthread) with high thread count for WebSocket/long-polling support.
web: gunicorn -w 1 --threads 100 --timeout 300 --bind 0.0.0.0:$PORT app:app
