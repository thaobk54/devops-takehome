"""Phase 7 - troubleshooting fixes are correct AND least-privilege (TC-7.1 .. TC-7.4).

Run after scripts/30-troubleshoot.sh. Launches short-lived curl pods with
different labels and checks what the NetworkPolicies allow / deny.
"""
import subprocess
import uuid

import pytest

from conftest import kjson, kubectl

NS = "troubleshoot"
WEB = "http://web-svc.troubleshoot.svc.cluster.local"


def run_curl(label, url, timeout=4):
    """Run a one-shot curl pod with label app=<label>; return (exit_ok, output)."""
    name = f"np-{label}-{uuid.uuid4().hex[:5]}"
    r = subprocess.run(
        ["kubectl", "-n", NS, "run", name, "--rm", "-i", "--restart=Never", "--quiet",
         "--image=curlimages/curl:8.7.1", f"--labels=app={label}",
         "--pod-running-timeout=90s", "--",
         # retries: kube-router programs a new pod's IP into the policy ipsets a
         # moment AFTER the pod starts - the provided smoke job retries for the
         # same reason. Retrying cannot turn a real "deny" into an "allow".
         "curl", "-sS", "--max-time", str(timeout), "--retry", "4", "--retry-delay", "1",
         "--retry-connrefused", "--retry-all-errors", url],
        capture_output=True, text=True, timeout=150)
    return r.returncode == 0, r.stdout + r.stderr


def test_tc_7_1_verify_passes():
    out = subprocess.run(["sh", "/work/troubleshoot/verify.sh"], capture_output=True, text=True)
    assert out.stdout.strip().splitlines()[-1] == "PASS", out.stdout[-500:]


def test_default_deny_untouched():
    np = kjson("get", "networkpolicy", "default-deny", "-n", NS)
    assert np["spec"]["podSelector"] == {}
    assert sorted(np["spec"]["policyTypes"]) == ["Egress", "Ingress"]


def test_allowed_path_smoke_client_reaches_web():
    ok, out = run_curl("smoke-client", WEB)
    assert ok and "TROUBLESHOOT-OK" in out, out


def test_tc_7_2_other_pods_cannot_reach_web():
    ok, out = run_curl("intruder", WEB)
    assert not ok, f"pod without the smoke-client label reached web: {out}"


def test_tc_7_3_smoke_client_cannot_reach_anything_else():
    # kubernetes API (ClusterIP of svc/kubernetes) - not needed by the client
    api_ip = kjson("get", "svc", "kubernetes", "-n", "default")["spec"]["clusterIP"]
    ok, out = run_curl("smoke-client", f"https://{api_ip}:443/version")
    assert not ok, out


def test_tc_7_4_nodes_untouched(nodes):
    caps = [v["capacity"] for v in nodes.values()]
    assert caps.count("spot") >= 2 and caps.count("on-demand") >= 1
    gpu = [n for n, v in nodes.items() if v["gpu"]]
    assert gpu and "nvidia.com/gpu" in nodes[gpu[0]]["taints"]


def test_ai_inference_on_gpu_node(nodes):
    pod = kjson("get", "pods", "-n", NS, "-l", "app=ai-inference")["items"][0]
    assert nodes[pod["spec"]["nodeName"]]["gpu"]
