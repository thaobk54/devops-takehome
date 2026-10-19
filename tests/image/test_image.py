"""Container image tests (Phase 2: TC-2.1 .. TC-2.4).

Prerequisite: image already built, e.g.
    docker build -t quote-api:test app/
Run:
    IMAGE=quote-api:test python -m pytest tests/image -v
Talks to the local Docker daemon through the `docker` CLI only (no SDK needed).
"""
import json
import os
import subprocess
import time
import urllib.request

import pytest

IMAGE = os.getenv("IMAGE", "quote-api:test")
MAX_SIZE_MB = 200
PORT = int(os.getenv("TEST_PORT", "18000"))


def sh(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True).stdout.strip()


def test_tc_2_1_image_exists():
    assert sh("docker", "image", "inspect", IMAGE, "--format", "{{.Id}}").startswith("sha256:")


def test_tc_2_2_runs_as_non_root():
    cfg = json.loads(sh("docker", "image", "inspect", IMAGE, "--format", "{{json .Config}}"))
    assert cfg["User"].split(":")[0] == "10001"           # numeric UID declared in image
    assert sh("docker", "run", "--rm", "--entrypoint", "id", IMAGE, "-u") == "10001"


def test_tc_2_4_image_size():
    size_mb = int(sh("docker", "image", "inspect", IMAGE, "--format", "{{.Size}}")) / 1e6
    assert size_mb < MAX_SIZE_MB, f"{size_mb:.0f} MB"


def test_no_build_tools_in_runtime():
    # multi-stage: the runtime layer must not ship gcc / a pip cache
    out = sh("docker", "run", "--rm", "--entrypoint", "sh", IMAGE, "-c",
             "command -v gcc || echo none; du -sm /root/.cache 2>/dev/null || echo nocache")
    assert "none" in out and "nocache" in out


@pytest.fixture(scope="module")
def readonly_container():
    """Run exactly like k8s will: read-only rootfs, only /tmp writable, all caps dropped."""
    name = "quote-api-imagetest"
    sh("docker", "rm", "-f", name, check=False)
    sh("docker", "run", "-d", "--name", name, "--read-only", "--tmpfs", "/tmp",
       "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
       "-p", f"127.0.0.1:{PORT}:8000", IMAGE)
    base = f"http://127.0.0.1:{PORT}"
    for _ in range(40):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    yield base
    sh("docker", "rm", "-f", name, check=False)


def test_tc_2_3_works_with_readonly_rootfs(readonly_container):
    base = readonly_container
    assert urllib.request.urlopen(base + "/healthz").status == 200
    assert urllib.request.urlopen(base + "/readyz").status == 200
    body = json.load(urllib.request.urlopen(base + "/api/quote"))
    assert body["quote"]
    metrics = urllib.request.urlopen(base + "/metrics").read().decode()
    assert 'quote_http_requests_total{method="GET",path="/api/quote",status="200"}' in metrics


def test_probes_answer_while_cpu_busy(readonly_container):
    """gthread workers: /healthz must stay fast while quote requests burn CPU."""
    import concurrent.futures as cf
    base = readonly_container

    def get(url):
        with urllib.request.urlopen(url, timeout=10) as r:
            r.read()

    with cf.ThreadPoolExecutor(8) as pool:
        futures = [pool.submit(get, base + "/api/quote") for _ in range(8)]
        time.sleep(0.1)                      # let the quote requests start burning CPU
        t0 = time.perf_counter()
        get(base + "/healthz")
        health_latency = time.perf_counter() - t0
        for f in futures:
            f.result()
    assert health_latency < 2.0, health_latency
