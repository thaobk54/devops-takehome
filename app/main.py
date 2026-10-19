"""quote-api: tiny HTTP service for the DevOps take-home.

Endpoints
  GET /healthz    liveness  - "the process is alive", never checks dependencies
  GET /readyz     readiness - "send me traffic"; 503 while not ready
  GET /metrics    Prometheus exposition format
  GET /api/quote  random quote as JSON, after ~100 ms of real CPU work

Run locally:   python main.py                 (Flask dev server)
In container:  gunicorn (see Dockerfile)      (1 worker, N threads)
"""
import hashlib
import os
import random
import time

from flask import Flask, Response, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# --- configuration (12-factor: everything via env vars) -----------------------
CPU_WORK_MS = float(os.getenv("CPU_WORK_MS", "100"))  # simulated CPU per request
APP_VERSION = os.getenv("APP_VERSION", "dev")          # injected = git SHA at build

QUOTES = [
    {"quote": "The best way to get started is to quit talking and begin doing.", "author": "Walt Disney"},
    {"quote": "It always seems impossible until it's done.", "author": "Nelson Mandela"},
    {"quote": "Don't watch the clock; do what it does. Keep going.", "author": "Sam Levenson"},
    {"quote": "Quality is not an act, it is a habit.", "author": "Aristotle"},
    {"quote": "Well done is better than well said.", "author": "Benjamin Franklin"},
    {"quote": "Simplicity is prerequisite for reliability.", "author": "Edsger W. Dijkstra"},
]

# --- metrics -------------------------------------------------------------------
# Labels use the matched route template (e.g. "/api/quote"), never the raw URL,
# so random 404 paths cannot explode label cardinality.
REQUESTS = Counter("quote_http_requests_total", "HTTP requests handled",
                   ["method", "path", "status"])
LATENCY = Histogram("quote_http_request_duration_seconds", "HTTP request latency",
                    ["path"], buckets=(0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1, 2, 5))
QUOTES_SERVED = Counter("quote_served_total", "Quotes returned to clients")
BUILD_INFO = Gauge("quote_build_info", "Build information", ["version"])
BUILD_INFO.labels(version=APP_VERSION).set(1)

app = Flask(__name__)
_state = {"ready": False}


def set_ready(value: bool) -> None:
    """Flip readiness (used at startup and by tests)."""
    _state["ready"] = value


def burn_cpu(ms: float) -> int:
    """Do real CPU work for `ms` milliseconds of *this thread's* CPU time.

    time.thread_time() counts only CPU consumed by the current thread, so the
    work stays ~ms per request even when several requests run concurrently in
    gunicorn threads (wall time grows under load - exactly what a CPU-bound
    service does, and what makes CPU-based HPA meaningful in Part 6).
    """
    deadline = time.thread_time() + ms / 1000.0
    digest, rounds = b"seed", 0
    while time.thread_time() < deadline:
        digest = hashlib.sha256(digest).digest()
        rounds += 1
    return rounds


# --- request instrumentation (one place, applies to every route) --------------
@app.before_request
def _start_timer():
    g.start = time.perf_counter()


@app.after_request
def _record_metrics(response):
    path = request.url_rule.rule if request.url_rule else "unmatched"
    if path != "/metrics":  # don't let scrapes pollute the app's own numbers
        REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        LATENCY.labels(path).observe(time.perf_counter() - g.start)
    return response


# --- routes ----------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return "ok", 200


@app.get("/readyz")
def readyz():
    if _state["ready"]:
        return "ready", 200
    return "not ready", 503


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.get("/api/quote")
def quote():
    rounds = burn_cpu(CPU_WORK_MS)
    QUOTES_SERVED.inc()
    item = random.choice(QUOTES)
    return jsonify(quote=item["quote"], author=item["author"],
                   version=APP_VERSION, hash_rounds=rounds,
                   host=os.getenv("HOSTNAME", "local"))


# Module imported (by gunicorn or tests) and quotes loaded => ready.
set_ready(len(QUOTES) > 0)

if __name__ == "__main__":
    # Dev server only (the container runs gunicorn): loopback by default.
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
