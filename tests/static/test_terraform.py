"""Part 5b checks for the Cloudflare Terraform (iac/cloudflare).

Static requirement checks always run; the negative `terraform validate` test
runs where terraform + registry access exist (the toolbox), else it is skipped.
"""
import os
import pathlib
import re
import shutil
import subprocess

import pytest

DIR = pathlib.Path(__file__).resolve().parents[2] / "iac" / "cloudflare"
ALL = "\n".join(p.read_text() for p in sorted(DIR.glob("*.tf")))


def block(kind, name):
    m = re.search(rf'{kind} "[^"]+" "{name}" \{{(.*?)\n\}}', ALL, re.S)
    assert m, f"{kind}.{name} not found"
    return m.group(1)


def test_provider_pinned_to_v5():
    assert re.search(r'source\s*=\s*"cloudflare/cloudflare"', ALL)
    assert re.search(r'version\s*=\s*"~> 5\.\d+"', ALL)
    assert (DIR / ".terraform.lock.hcl").exists()          # reproducible provider builds


def test_quote_api_record_is_proxied():
    b = block("resource", "quote_api")
    assert 'name    = "quote-api.example.com"' in b
    assert re.search(r"proxied\s*=\s*true", b)


def test_import_block_adopts_existing_record():
    m = re.search(r"import \{(.*?)\n\}", ALL, re.S)
    assert m, "no import block"
    assert "to = cloudflare_dns_record.status_legacy" in m.group(1)
    block("resource", "status_legacy")                      # target resource exists


def test_cache_rules():
    b = block("resource", "quote_api_cache")
    assert 'phase       = "http_request_cache_settings"' in b
    bypass = b[b.index('ref         = "bypass_api"'):]
    assert "/api/" in bypass and re.search(r"cache\s*=\s*false", bypass)
    static = b[b.index('ref         = "cache_static_assets"'):b.index('ref         = "bypass_api"')]
    assert re.search(r"cache\s*=\s*true", static) and "edge_ttl" in static
    # bypass must come AFTER the static rule (later matching rules win)
    assert b.index("cache_static_assets") < b.index("bypass_api")


def test_no_credentials_in_code():
    assert not re.search(r"api_(token|key)\s*=", ALL)


@pytest.mark.skipif(not shutil.which("terraform"), reason="terraform not installed")
def test_validate_catches_v4_syntax(tmp_path):
    """`validate` must be a real gate: v4-style `value =` on a v5 record fails."""
    work = tmp_path / "cf"
    shutil.copytree(DIR, work, ignore=shutil.ignore_patterns(".terraform"))
    env = {**os.environ, "TF_DATA_DIR": str(tmp_path / "data"),
           "TF_PLUGIN_CACHE_DIR": os.environ.get("TF_PLUGIN_CACHE_DIR", "/root/.cache/tf-plugins")}
    os.makedirs(env["TF_PLUGIN_CACHE_DIR"], exist_ok=True)
    init = subprocess.run(["terraform", f"-chdir={work}", "init", "-backend=false", "-input=false"],
                          capture_output=True, text=True, env=env)
    if init.returncode != 0:
        pytest.skip("registry not reachable: " + init.stderr[-200:])
    ok = subprocess.run(["terraform", f"-chdir={work}", "validate"], capture_output=True, text=True, env=env)
    assert ok.returncode == 0, ok.stderr
    main = work / "main.tf"
    main.write_text(main.read_text().replace("content = var.origin_hostname", "value   = var.origin_hostname"))
    bad = subprocess.run(["terraform", f"-chdir={work}", "validate"], capture_output=True, text=True, env=env)
    assert bad.returncode != 0
