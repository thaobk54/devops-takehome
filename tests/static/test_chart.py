"""Static policy tests for the Helm chart (Phase 4: TC-4.1 .. TC-4.3).

No cluster needed - only `helm`. Run in the toolbox (or CI):
    python3 -m pytest tests/static -v
Each test encodes one requirement of the assignment, so a regression in the
chart fails loudly instead of being discovered during the reclaim drill.
"""
import pathlib
import subprocess

import pytest
import yaml

CHART = str(pathlib.Path(__file__).resolve().parents[2] / "charts" / "quote-api")
TAG = "0123abc"


def render(*extra):
    out = subprocess.run(
        ["helm", "template", "quote-api", CHART, "-n", "quote-api", "--set", f"image.tag={TAG}", *extra],
        check=True, capture_output=True, text=True).stdout
    return {f"{d['kind']}/{d['metadata']['name']}": d for d in yaml.safe_load_all(out) if d}


@pytest.fixture(scope="module")
def objs():
    return render()


@pytest.fixture(scope="module")
def pod(objs):
    return objs["Deployment/quote-api"]["spec"]["template"]["spec"]


def test_tc_4_1_helm_lint():
    subprocess.run(["helm", "lint", "--strict", CHART, "--set", f"image.tag={TAG}"],
                   check=True, capture_output=True)


def test_required_objects_exist(objs):
    for k in ["Deployment", "Service", "Ingress", "HorizontalPodAutoscaler",
              "PodDisruptionBudget", "ServiceAccount", "NetworkPolicy"]:
        assert f"{k}/quote-api" in objs, k


def test_hpa_min_3(objs):
    hpa = objs["HorizontalPodAutoscaler/quote-api"]["spec"]
    assert hpa["minReplicas"] == 3 and hpa["maxReplicas"] > 3


def test_deployment_has_no_replicas_when_hpa_on(objs):
    # if Deployment.spec.replicas were set, every ArgoCD sync would undo HPA scaling
    assert "replicas" not in objs["Deployment/quote-api"]["spec"]


def test_pdb_keeps_majority(objs):
    assert objs["PodDisruptionBudget/quote-api"]["spec"]["maxUnavailable"] == 1


def test_image_tag_is_immutable(pod):
    image = pod["containers"][0]["image"]
    assert image.endswith(":" + TAG)
    for bad in ["latest", ""]:
        r = subprocess.run(["helm", "template", "x", CHART, "--set", f"image.tag={bad}"],
                           capture_output=True, text=True)
        assert r.returncode != 0 and "immutable git SHA" in r.stderr


def test_probes_and_resources(pod):
    c = pod["containers"][0]
    for p in ["startupProbe", "livenessProbe", "readinessProbe"]:
        assert p in c
    assert c["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert c["readinessProbe"]["httpGet"]["path"] == "/readyz"
    for kind in ["requests", "limits"]:
        assert {"cpu", "memory"} <= set(c["resources"][kind])


def test_security_context(pod):
    c = pod["containers"][0]["securityContext"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert c["readOnlyRootFilesystem"] is True
    assert c["allowPrivilegeEscalation"] is False
    assert c["capabilities"]["drop"] == ["ALL"]
    assert pod["automountServiceAccountToken"] is False


def test_placement_hard_affinity_excludes_gpu_and_unlabeled(pod):
    req = pod["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
    expr = req["nodeSelectorTerms"][0]["matchExpressions"][0]
    assert expr["key"] == "acme.io/capacity" and expr["operator"] == "In"
    assert sorted(expr["values"]) == ["on-demand", "spot"]
    # must NOT tolerate the GPU taint
    assert not any(t.get("key") == "nvidia.com/gpu" for t in pod.get("tolerations", []))


def test_placement_prefers_spot(pod):
    pref = pod["affinity"]["nodeAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"]
    assert pref[0]["preference"]["matchExpressions"][0]["values"] == ["spot"]
    assert pref[0]["weight"] == 100


def test_placement_spread_constraints(pod):
    tsc = {t["topologyKey"]: t for t in pod["topologySpreadConstraints"]}
    # hard across capacity types => >=1 replica on on-demand
    assert tsc["acme.io/capacity"]["whenUnsatisfiable"] == "DoNotSchedule"
    assert tsc["acme.io/capacity"]["maxSkew"] == 1
    # soft across nodes => a drained node never leaves pods Pending
    assert tsc["kubernetes.io/hostname"]["whenUnsatisfiable"] == "ScheduleAnyway"


def test_not_hard_pinned_to_on_demand(pod):
    # "Hard-pinning all replicas to on-demand scores zero"
    assert "nodeSelector" not in pod
    req = pod["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
    assert "spot" in req["nodeSelectorTerms"][0]["matchExpressions"][0]["values"]


def test_ingress_routes_to_service(objs):
    rule = objs["Ingress/quote-api"]["spec"]["rules"][0]
    backend = rule["http"]["paths"][0]["backend"]["service"]
    assert backend["name"] == "quote-api"
    assert objs["Ingress/quote-api"]["spec"]["ingressClassName"] == "traefik"
