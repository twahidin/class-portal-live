# timeout 300: textbook PDF ingest can take 1–3 min.
# workers 1, threads 4: Minimize memory on Railway free tier.
# Threading supports Flask-SocketIO WebSocket connections.
web: gunicorn --worker-class gthread -w 1 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT app:app
