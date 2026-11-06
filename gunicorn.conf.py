import os

port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"
workers = 1
threads = 4
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"

print(f"[gunicorn.conf.py] Binding Gunicorn to {bind} with 1 worker and 4 threads")
