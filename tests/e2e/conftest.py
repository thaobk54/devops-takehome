"""Shared helpers for the end-to-end suite (runs INSIDE the toolbox).

    docker compose exec toolbox python3 -m pytest /work/tests/e2e -v
Everything goes through `kubectl ... -o json`, so the tests assert on the
same API objects an operator would look at.
"""
import json
import subprocess

import pytest


def kubectl(*args, check=True):
    r = subprocess.run(["kubectl", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"kubectl {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def kjson(*args):
    return json.loads(kubectl(*args, "-o", "json"))


@pytest.fixture(scope="session")
def nodes():
    """node name -> labels/taints/role, e.g. nodes['k3d-acme-agent-0']['capacity']"""
    out = {}
    for n in kjson("get", "nodes")["items"]:
        labels = n["metadata"]["labels"]
        out[n["metadata"]["name"]] = {
            "capacity": labels.get("acme.io/capacity"),
            "gpu": labels.get("acme.io/node-type") == "gpu",
            "control_plane": "node-role.kubernetes.io/control-plane" in labels,
            "taints": [t["key"] for t in n["spec"].get("taints", [])],
            "ready": any(c["type"] == "Ready" and c["status"] == "True"
                         for c in n["status"]["conditions"]),
        }
    return out
