"""Deliverable checks for the documentation (assignment checklist as tests)."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(name):
    return (ROOT / name).read_text()


def test_required_files_exist():
    for f in ["README.md", "TROUBLESHOOTING.md", "AI-USAGE.md", "OPS-ANSWERS.md",
              "MIGRATION-NOTES.md", "troubleshoot/fixed-app.yaml", "docker-compose.yml",
              ".github/workflows/ci.yml", "scripts/50-validate-tf.sh"]:
        assert (ROOT / f).is_file(), f


def test_readme_sections():
    r = read("README.md")
    for h in ["## Quick start", "## Architecture", "## Script reference",
              "## Design decisions & trade-offs", "## Troubleshooting"]:
        assert h in r, h
    assert r.count("```mermaid") >= 2          # architecture + AWS bonus
    assert "docker compose up -d" in r and "./scripts/run-all.sh" in r


def test_every_script_is_documented():
    r = read("README.md")
    scripts = [p.name for p in (ROOT / "scripts").glob("*.sh") if p.name != "lib.sh"]
    missing = [s for s in scripts if f"scripts/{s}" not in r]
    assert not missing, missing


def test_readme_links_resolve():
    for link in re.findall(r"\]\(([^)#:]+\.md)\)", read("README.md")):
        assert (ROOT / link).is_file(), link


def test_ops_answers_four_questions_and_short():
    o = read("OPS-ANSWERS.md")
    assert len(re.findall(r"^## [1-4]\. ", o, re.M)) == 4
    assert len(o.split()) <= 900, len(o.split())   # "max 1.5 pages"


def test_troubleshooting_covers_each_issue():
    t = read("TROUBLESHOOTING.md")
    for word in ["Symptom", "Diagnosis", "Root cause", "Fix"]:
        assert t.count(word) >= 8, word
    fixes = set(re.findall(r"FIX #(\d+)", read("troubleshoot/fixed-app.yaml")))
    assert {str(i) for i in range(1, 9)} <= fixes


def test_ai_usage_has_wrong_example():
    a = read("AI-USAGE.md")
    assert "wrong" in a.lower() and "prompt" in a.lower()


def test_no_secrets_committed():
    pat = re.compile(r"(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
    offenders = []
    for p in ROOT.rglob("*"):
        if p.is_file() and ".git" not in p.parts and p.suffix not in {".png", ".tgz"}:
            if p.name == "legacy.gitlab-ci.yml":
                continue                              # provided fixture, AWS doc example keys
            if pat.search(p.read_text(errors="ignore")):
                offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, offenders
