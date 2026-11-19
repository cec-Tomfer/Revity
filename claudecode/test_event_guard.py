"""Prove automatiche per la correzione 3 (eventi e origine delle PR). Solo dati finti."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from claudecode.event_guard import check_event

REPO = "example-org/example-repo"


def _event(tmp_path, head_repo="same", fork=False, base_repo=REPO):
    pr = {
        "number": 7,
        "base": {"repo": {"full_name": base_repo}},
        "head": {"sha": "abc", "repo": None},
    }
    if head_repo == "same":
        pr["head"]["repo"] = {"full_name": base_repo, "fork": fork}
    elif head_repo is not None:
        pr["head"]["repo"] = {"full_name": head_repo, "fork": fork}
    path = tmp_path / "event.json"
    path.write_text(json.dumps({"pull_request": pr}))
    return str(path)


def test_same_repo_pull_request_is_accepted(tmp_path):
    ok, msg = check_event("pull_request", _event(tmp_path), REPO)
    assert ok, msg


@pytest.mark.parametrize("name", ["pull_request_target", "push", "workflow_dispatch", "", None])
def test_other_events_are_refused_with_message(tmp_path, name):
    ok, msg = check_event(name, _event(tmp_path), REPO)
    assert not ok
    assert "pull_request" in msg


def test_fork_is_refused(tmp_path):
    ok, msg = check_event("pull_request", _event(tmp_path, head_repo="evil/example-repo", fork=True), REPO)
    assert not ok and "fork" in msg.lower()


def test_head_repo_different_even_without_fork_flag_is_refused(tmp_path):
    ok, _ = check_event("pull_request", _event(tmp_path, head_repo="evil/other", fork=False), REPO)
    assert not ok


def test_deleted_fork_head_repo_none_is_refused(tmp_path):
    ok, msg = check_event("pull_request", _event(tmp_path, head_repo=None), REPO)
    assert not ok and "cancellat" in msg


def test_case_insensitive_same_repo(tmp_path):
    ok, msg = check_event("pull_request", _event(tmp_path, head_repo="EXAMPLE-Org/Example-Repo"), REPO)
    assert ok, msg


def test_base_repo_must_match_github_repository(tmp_path):
    ok, _ = check_event("pull_request", _event(tmp_path), "altro/repo")
    assert not ok


def test_missing_or_broken_event_file_is_refused(tmp_path):
    assert not check_event("pull_request", str(tmp_path / "nope.json"), REPO)[0]
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert not check_event("pull_request", str(bad), REPO)[0]
    assert not check_event("pull_request", None, REPO)[0]


def test_cli_exit_codes(tmp_path):
    script = Path(__file__).parent / "event_guard.py"
    base = {"PATH": "/usr/bin:/bin"}
    ok = subprocess.run(
        [sys.executable, "-I", str(script)],
        env={**base, "GITHUB_EVENT_NAME": "pull_request",
             "GITHUB_EVENT_PATH": _event(tmp_path), "GITHUB_REPOSITORY": REPO},
        capture_output=True, text=True,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    bad = subprocess.run(
        [sys.executable, "-I", str(script)],
        env={**base, "GITHUB_EVENT_NAME": "pull_request_target",
             "GITHUB_EVENT_PATH": _event(tmp_path), "GITHUB_REPOSITORY": REPO},
        capture_output=True, text=True,
    )
    assert bad.returncode == 3
    assert "::error::" in bad.stdout
