"""Part 5a policy tests for the Karpenter GPU manifests (no cluster needed).

Schema validity is checked separately, server-side against the real CRDs, by
scripts/50-validate-tf.sh. These tests pin the *design* requirements.
"""
import pathlib

import pytest
import yaml

DIR = pathlib.Path(__file__).resolve().parents[2] / "iac" / "karpenter"


def load_all():
    docs = []
    for f in sorted(DIR.glob("*.yaml")):
        docs += [d for d in yaml.safe_load_all(f.read_text()) if d]
    return docs


@pytest.fixture(scope="module")
def docs():
    return load_all()


@pytest.fixture(scope="module")
def pools(docs):
    return {d["metadata"]["name"]: d for d in docs if d["kind"] == "NodePool"}


def req(pool, key):
    for r in pool["spec"]["template"]["spec"]["requirements"]:
        if r["key"] == key:
            return r
    return None


def test_current_stable_api_versions(docs):
    kinds = {d["kind"]: d["apiVersion"] for d in docs}
    assert kinds["NodePool"] == "karpenter.sh/v1"            # not v1beta1 / v1alpha5
    assert kinds["EC2NodeClass"] == "karpenter.k8s.aws/v1"   # not AWSNodeTemplate
    assert "Provisioner" not in kinds and "AWSNodeTemplate" not in kinds


def test_spot_preferred_on_demand_fallback_by_weight(pools):
    spot = [p for p in pools.values() if req(p, "karpenter.sh/capacity-type")["values"] == ["spot"]]
    od = [p for p in pools.values() if req(p, "karpenter.sh/capacity-type")["values"] == ["on-demand"]]
    assert len(spot) == 1 and len(od) == 1
    assert spot[0]["spec"]["weight"] > od[0]["spec"]["weight"]


@pytest.mark.parametrize("name", ["gpu-spot", "gpu-on-demand"])
def test_gpu_taint(pools, name):
    taints = pools[name]["spec"]["template"]["spec"]["taints"]
    assert {"key": "nvidia.com/gpu", "value": "true", "effect": "NoSchedule"} in taints


@pytest.mark.parametrize("name", ["gpu-spot", "gpu-on-demand"])
def test_consolidation_does_not_kill_running_inference(pools, name):
    d = pools[name]["spec"]["disruption"]
    # WhenEmptyOrUnderutilized would evict pods to bin-pack -> mid-request kills
    assert d["consolidationPolicy"] == "WhenEmpty"
    assert d["consolidateAfter"] not in ("0s", None)
    assert {"nodes": "1"} in d["budgets"]                  # one node at a time
    tgp = pools[name]["spec"]["template"]["spec"]["terminationGracePeriod"]
    assert tgp.endswith("h")                               # bounded drain time for long requests


@pytest.mark.parametrize("name", ["gpu-spot", "gpu-on-demand"])
def test_limits_cap_spend(pools, name):
    limits = pools[name]["spec"]["limits"]
    assert int(limits["nvidia.com/gpu"]) > 0
    assert "cpu" in limits and "memory" in limits


def test_spot_pool_is_diversified(pools):
    fam = req(pools["gpu-spot"], "karpenter.k8s.aws/instance-family")
    assert len(fam["values"]) >= 3 and fam.get("minValues", 1) >= 2
    zones = req(pools["gpu-spot"], "topology.kubernetes.io/zone")
    assert len(zones["values"]) >= 2


def test_nodeclass_hardening(docs):
    nc = next(d for d in docs if d["kind"] == "EC2NodeClass")["spec"]
    assert nc["metadataOptions"]["httpTokens"] == "required"           # IMDSv2
    assert nc["metadataOptions"]["httpPutResponseHopLimit"] == 1
    assert all(b["ebs"]["encrypted"] for b in nc["blockDeviceMappings"])
    assert nc["amiSelectorTerms"][0]["alias"].startswith("al2023@")
