# timeout 300: textbook PDF ingest (embed + Pinecone) can take 1–3 min for larger files
web: gunicorn app:app --workers 2 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT
