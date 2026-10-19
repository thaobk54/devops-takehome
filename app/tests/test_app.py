"""Unit tests for quote-api (Phase 1 test cases TC-1.1 .. TC-1.6).

Run:  cd app && python -m pytest -v
Uses Flask's in-process test client: no network, no container needed.
"""
import time

import pytest

import main


@pytest.fixture()
def client():
    main.set_ready(True)
    main.app.config.update(TESTING=True)
    with main.app.test_client() as c:
        yield c
    main.set_ready(True)


def metric_value(client, name, **labels):
    """Read one sample value from /metrics (0.0 if the series doesn't exist yet)."""
    from prometheus_client.parser import text_string_to_metric_families
    text = client.get("/metrics").get_data(as_text=True)
    for family in text_string_to_metric_families(text):
        for s in family.samples:
            if s.name == name and all(s.labels.get(k) == v for k, v in labels.items()):
                return s.value
    return 0.0


def test_tc_1_1_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_data(as_text=True) == "ok"


def test_tc_1_2_readyz_toggles(client):
    assert client.get("/readyz").status_code == 200
    main.set_ready(False)
    assert client.get("/readyz").status_code == 503
    # liveness must NOT depend on readiness (otherwise k8s would kill a pod that
    # is merely warming up / draining)
    assert client.get("/healthz").status_code == 200


def test_tc_1_3_quote_json(client):
    r = client.get("/api/quote")
    assert r.status_code == 200
    assert r.is_json
    body = r.get_json()
    assert body["quote"] and body["author"]
    assert {"quote": body["quote"], "author": body["author"]} in main.QUOTES


def test_tc_1_4_cpu_work_is_real_and_about_100ms():
    # Measure CPU time of the calling thread: sleep() would give ~0 here.
    t0 = time.thread_time()
    rounds = main.burn_cpu(100)
    cpu_ms = (time.thread_time() - t0) * 1000
    assert 80 <= cpu_ms <= 150, cpu_ms
    assert rounds > 1000  # hashing actually happened


def test_tc_1_5_metrics_counter_increments(client):
    before = metric_value(client, "quote_http_requests_total",
                          method="GET", path="/api/quote", status="200")
    client.get("/api/quote")
    client.get("/api/quote")
    after = metric_value(client, "quote_http_requests_total",
                         method="GET", path="/api/quote", status="200")
    assert after - before == 2
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.content_type.startswith("text/plain")
    assert "quote_http_request_duration_seconds_bucket" in r.get_data(as_text=True)


def test_tc_1_6_unknown_path_404_counted_without_cardinality(client):
    before = metric_value(client, "quote_http_requests_total", path="unmatched", status="404")
    assert client.get("/random-abc-123").status_code == 404
    after = metric_value(client, "quote_http_requests_total", path="unmatched", status="404")
    assert after - before == 1
    assert "random-abc-123" not in client.get("/metrics").get_data(as_text=True)
