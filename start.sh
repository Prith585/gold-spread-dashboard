#!/bin/sh
PORT="${PORT:-10000}"
echo "Starting Gold Spread Terminal on 0.0.0.0:$PORT..."
exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 app:app
