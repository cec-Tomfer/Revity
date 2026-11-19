"""Prove automatiche per la correzione 1 (versioni fissate). Controllano i file, nessuna rete."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ACTION = (ROOT / "action.yml").read_text()
WORKFLOWS = [p for p in (ROOT / ".github" / "workflows").glob("*.yml")]


def _uses(text):
    return re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", text, flags=re.MULTILINE)


@pytest.mark.parametrize("name,text", [("action.yml", ACTION)] + [(p.name, p.read_text()) for p in WORKFLOWS])
def test_every_external_action_pinned_to_full_sha(name, text):
    for ref in _uses(text):
        if ref.startswith("./"):
            continue
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"{name}: {ref}"


@pytest.mark.parametrize("name,text", [("action.yml", ACTION)] + [(p.name, p.read_text()) for p in WORKFLOWS])
def test_npm_global_installs_have_exact_version(name, text):
    for m in re.finditer(r"npm install -g (\S+)", text):
        assert re.search(r"@\d+\.\d+\.\d+$", m.group(1)), f"{name}: {m.group(1)}"


def test_no_floating_refs_or_runtime_versions():
    for name, text in [("action.yml", ACTION)] + [(p.name, p.read_text()) for p in WORKFLOWS]:
        assert "@main" not in text and "@master" not in text, name
        assert not re.search(r"(python|node|bun)-version:\s*['\"]?(latest|\d+\.x|x)\b", text), name
    assert re.search(r"python-version:\s*'3\.\d+'", ACTION)
    assert re.search(r"node-version:\s*'\d+'", ACTION)


def test_pip_installs_use_hashes():
    for name, text in [("action.yml", ACTION)] + [(p.name, p.read_text()) for p in WORKFLOWS]:
        for line in re.findall(r"pip install .*", text):
            if "-r" in line:
                assert "--require-hashes" in line, f"{name}: {line}"


def test_no_unpinned_apt_installs():
    assert "apt-get install" not in ACTION


def test_requirements_txt_exact_pins():
    lines = [l.strip() for l in (ROOT / "claudecode" / "requirements.txt").read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]
    assert lines
    for l in lines:
        assert re.fullmatch(r"[A-Za-z0-9_.-]+==\d+(\.\d+)*", l), l


def test_lock_every_package_has_hashes_and_exact_version():
    text = (ROOT / "claudecode" / "requirements.lock").read_text()
    blocks = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", text)
    pkgs = [b for b in blocks if re.match(r"[A-Za-z0-9_.-]+==\d", b)]
    assert len(pkgs) >= 5
    for b in pkgs:
        assert re.search(r"--hash=sha256:[0-9a-f]{64}", b), b.splitlines()[0]
    # le versioni dirette coincidono con requirements.txt
    for l in (ROOT / "claudecode" / "requirements.txt").read_text().splitlines():
        if "==" in l and not l.startswith("#"):
            assert re.search(rf"^{re.escape(l.strip())}\b", text, flags=re.MULTILINE), l


def test_action_installs_from_lock():
    assert "requirements.lock" in ACTION and "requirements.txt" not in ACTION


def test_yaml_parses_if_available():
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(ACTION)
    assert doc["runs"]["using"] == "composite"
    for step in doc["runs"]["steps"]:
        assert "name" in step
