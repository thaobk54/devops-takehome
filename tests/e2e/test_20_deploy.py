"""Phase 5 - GitOps deployment + placement (TC-5.1 .. TC-5.6).

Run after scripts/20-deploy.sh.
"""
import json
import os
import time
import urllib.request
from collections import Counter

import pytest

from conftest import kjson, kubectl

NS = "quote-api"
SEL = "app.kubernetes.io/name=quote-api"
INGRESS = os.getenv("INGRESS_URL", "http://k3d-acme-serverlb:80")


def app_pods():
    return [p for p in kjson("get", "pods", "-n", NS, "-l", SEL)["items"]
            if p["metadata"].get("deletionTimestamp") is None
            and p["status"].get("phase") == "Running"]


def wait_for(predicate, timeout=180, step=3):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(step)
    return False


def test_tc_5_1_argocd_ready():
    for d in kjson("get", "deploy", "-n", "argocd")["items"]:
        st = d["status"]
        assert st.get("readyReplicas", 0) == d["spec"]["replicas"], d["metadata"]["name"]


def test_tc_5_2_application_synced_healthy():
    # Poll: right after the reclaim drill ArgoCD briefly reports the HPA (and so
    # the App) as Degraded - new pods have no metrics yet (ScalingActive=False).
    def healthy():
        st = kjson("get", "application", "quote-api", "-n", "argocd")["status"]
        return st["sync"]["status"] == "Synced" and st["health"]["status"] == "Healthy"
    assert wait_for(healthy, timeout=180, step=5), \
        kubectl("-n", "argocd", "get", "application", "quote-api", "-o", "jsonpath={.status.health}")
    app = kjson("get", "application", "quote-api", "-n", "argocd")
    assert app["spec"]["source"]["path"] == "charts/quote-api"   # our own chart from Git


def test_not_installed_with_helm_directly():
    # "no manual helm install of your app": the only helm release is argocd itself
    out = kubectl("get", "secrets", "-A", "-l", "owner=helm", "-o",
                  "jsonpath={range .items[*]}{.metadata.labels.name}{' '}{end}")
    assert "quote-api" not in out.split()


def test_tc_5_3_three_ready_replicas_with_sha_tag():
    pods = app_pods()
    assert len(pods) >= 3
    for p in pods:
        image = p["spec"]["containers"][0]["image"]
        tag = image.rsplit(":", 1)[1]
        assert tag != "latest" and len(tag) >= 7, image
        assert all(c["ready"] for c in p["status"]["containerStatuses"])


def test_tc_5_4_placement(nodes):
    pods = app_pods()
    placed = Counter(nodes[p["spec"]["nodeName"]]["capacity"] for p in pods)
    on_gpu = [p for p in pods if nodes[p["spec"]["nodeName"]]["gpu"]]
    on_cp = [p for p in pods if nodes[p["spec"]["nodeName"]]["control_plane"]]
    assert placed["on-demand"] >= 1, placed          # availability
    assert placed["spot"] >= placed["on-demand"], placed  # cost: spot preferred
    assert not on_gpu and not on_cp
    # soft spread: replicas never all on one node. (After a drill two may share a
    # spot node - the spread is soft on purpose and nothing rebalances afterwards
    # without a descheduler; see README trade-offs.)
    assert len({p["spec"]["nodeName"] for p in pods}) >= 2


def test_tc_5_5_api_through_ingress():
    with urllib.request.urlopen(INGRESS + "/api/quote", timeout=10) as r:
        assert r.status == 200
        body = json.load(r)
    assert body["quote"] and body["author"]


def test_tc_5_6_selfheal_reverts_manual_drift():
    """kubectl edit of a Git-managed field must be reverted by ArgoCD."""
    kubectl("-n", NS, "patch", "svc", "quote-api", "--type=merge",
            "-p", '{"metadata":{"labels":{"app.kubernetes.io/version":"drift"}}}')
    reverted = wait_for(lambda: kjson("get", "svc", "quote-api", "-n", NS)
                        ["metadata"]["labels"]["app.kubernetes.io/version"] != "drift", timeout=120)
    assert reverted, "ArgoCD selfHeal did not revert the drift"


def test_hpa_and_pdb_active():
    hpa = kjson("get", "hpa", "quote-api", "-n", NS)
    assert hpa["spec"]["minReplicas"] == 3
    pdb = kjson("get", "pdb", "quote-api", "-n", NS)
    assert pdb["status"]["disruptionsAllowed"] >= 1   # drains can proceed one pod at a time
