"""Phase 3 - compose harness / cluster (TC-3.2, TC-3.3, TC-3.5)."""
import shutil
import subprocess

import pytest


def test_tc_3_2_five_ready_nodes(nodes):
    workers = [n for n, v in nodes.items() if not v["control_plane"]]
    assert len(nodes) >= 5 and len(workers) >= 4, nodes
    assert all(v["ready"] for v in nodes.values())


def test_tc_3_3_nodepool_labels_and_taints(nodes):
    caps = [v["capacity"] for v in nodes.values()]
    assert caps.count("spot") == 2
    assert caps.count("on-demand") == 1
    gpu = [n for n, v in nodes.items() if v["gpu"]]
    assert len(gpu) == 1
    assert "nvidia.com/gpu" in nodes[gpu[0]]["taints"]


@pytest.mark.parametrize("tool,args", [
    ("kubectl", ["version", "--client"]), ("helm", ["version"]),
    ("terraform", ["version"]), ("k6", ["version"]), ("k3d", ["version"]),
])
def test_tc_3_5_toolbox_has_tools(tool, args):
    assert shutil.which(tool), f"{tool} missing"
    subprocess.run([tool, *args], check=True, capture_output=True)


def test_scripts_are_bind_mounted():
    # /work is the host repo: the numbered scripts must be visible here
    import glob
    assert glob.glob("/work/scripts/[0-9][0-9]-*.sh")


def test_no_node_left_cordoned():
    # the reclaim drill must always uncordon its victim
    from conftest import kjson
    cordoned = [n["metadata"]["name"] for n in kjson("get", "nodes")["items"]
                if n["spec"].get("unschedulable")]
    assert not cordoned, cordoned
