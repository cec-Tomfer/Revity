"""Prove automatiche per la correzione 4 (tetto di esecuzioni per PR). Solo dati finti, nessuna rete."""

import json
import os
import re

import pytest

from claudecode import run_budget as rb

REPO = "example-org/example-repo"


class FakeGitHub:
    """Simula l'API dei commenti di una PR, con paginazione a 100."""

    def __init__(self, comments=None):
        self.comments = list(comments or [])
        self.calls = []
        self._id = 1000

    def __call__(self, method, path, data=None):
        self.calls.append((method, path))
        if method == "GET":
            m = re.search(r"[&?]page=(\d+)", path)
            page = int(m.group(1)) if m else 1
            return self.comments[(page - 1) * 100: page * 100]
        if method == "POST":
            self._id += 1
            c = {"id": self._id, "body": data["body"], "user": {"type": "Bot"}}
            self.comments.append(c)
            return c
        if method == "PATCH":
            cid = int(path.rsplit("/", 1)[1])
            for c in self.comments:
                if c["id"] == cid:
                    c["body"] = data["body"]
                    return c
        raise AssertionError((method, path))


def _counter_comment(n, sha, notified=False, cid=1, user_type="Bot"):
    body = rb.render_body({"n": n, "sha": sha, "capped_notified": notified}, 5)
    return {"id": cid, "body": body, "user": {"type": user_type}}


def test_first_run_creates_counter_comment():
    gh = FakeGitHub()
    r = rb.reserve_run(gh, REPO, 7, "sha1", 5)
    assert r["enable"] and r["n"] == 1
    assert len(gh.comments) == 1 and rb.parse_counter(gh.comments[0]["body"])["n"] == 1


def test_runs_up_to_cap_then_stops_at_sixth_commit():
    gh = FakeGitHub()
    results = [rb.reserve_run(gh, REPO, 7, f"sha{i}", 5) for i in range(1, 8)]
    assert [r["enable"] for r in results] == [True] * 5 + [False] * 2
    assert "tetto" in results[5]["reason"].lower()
    assert len(gh.comments) == 1  # un solo commento sticky, aggiornato


def test_cap_message_written_once():
    gh = FakeGitHub()
    for i in range(1, 8):
        rb.reserve_run(gh, REPO, 7, f"sha{i}", 5)
    state = rb.parse_counter(gh.comments[0]["body"])
    assert state["capped_notified"] is True
    posts_before = [c for c in gh.calls if c[0] in ("POST", "PATCH")]
    rb.reserve_run(gh, REPO, 7, "sha99", 5)
    assert [c for c in gh.calls if c[0] in ("POST", "PATCH")] == posts_before  # nessuna scrittura


def test_same_commit_is_not_scanned_twice():
    gh = FakeGitHub([_counter_comment(2, "shaA")])
    r = rb.reserve_run(gh, REPO, 7, "shaA", 5)
    assert not r["enable"] and "già" in r["reason"]
    assert rb.parse_counter(gh.comments[0]["body"])["n"] == 2


def test_counter_found_even_beyond_first_page():
    filler = [{"id": i, "body": "x", "user": {"type": "User"}} for i in range(250)]
    gh = FakeGitHub(filler + [_counter_comment(4, "shaA", cid=9999)])
    r = rb.reserve_run(gh, REPO, 7, "shaB", 5)
    assert r["enable"] and r["n"] == 5
    assert not any(c[0] == "POST" for c in gh.calls)  # aggiorna, non ne crea un secondo


def test_forged_counter_from_human_is_ignored():
    forged = _counter_comment(5, "x", user_type="User")
    gh = FakeGitHub([forged])
    r = rb.reserve_run(gh, REPO, 7, "shaZ", 5)
    assert r["enable"] and r["n"] == 1


def test_broken_marker_treated_as_absent():
    assert rb.parse_counter("<!-- revity-run-counter {not json} -->") is None
    assert rb.parse_counter("<!-- revity-run-counter {\"n\": \"x\"} -->") is None
    assert rb.parse_counter("niente") is None
    assert rb.parse_counter(None) is None


def test_max_runs_parsing():
    assert rb.parse_max_runs(None) == 5
    assert rb.parse_max_runs("3") == 3
    for bad in ("0", "-1", "abc", "1000", ""):
        assert rb.parse_max_runs(bad) == 5


def test_api_error_fails_closed():
    def boom(method, path, data=None):
        raise OSError("rete giù")
    r = rb.reserve_run(boom, REPO, 7, "sha1", 5)
    assert not r["enable"] and r["error"]


def test_cli_writes_outputs_and_refuses_on_error(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    ev = tmp_path / "ev.json"
    ev.write_text(json.dumps({"pull_request": {"number": 7, "head": {"sha": "abc"}}}))
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(ev))
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("GITHUB_TOKEN", "finto")
    gh = FakeGitHub()
    code = rb.main(request=gh)
    assert code == 0
    text = out.read_text()
    assert "enable_claudecode=true" in text and "silence_claudecode_comments=false" in text
    # secondo giro sullo stesso commit: non abilitato
    out.write_text("")
    assert rb.main(request=gh) == 0
    assert "enable_claudecode=false" in out.read_text()


# ---- bozze, chiuse, bot (nessun consumo del tetto) ------------------------------------

def test_skip_reasons():
    assert rb.skip_reason({"draft": True}, {}) and "bozza" in rb.skip_reason({"draft": True}, {})
    assert rb.skip_reason({"state": "closed"}, {})
    assert rb.skip_reason({"user": {"type": "Bot"}}, {})
    assert rb.skip_reason({"draft": False, "state": "open", "user": {"type": "User"}}, {}) is None
    assert rb.skip_reason({}, {}) is None


def test_skip_can_be_disabled():
    assert rb.skip_reason({"draft": True}, {"REVITY_SKIP_DRAFTS": "false"}) is None
    assert rb.skip_reason({"user": {"type": "Bot"}}, {"REVITY_SKIP_BOTS": "false"}) is None


def test_cli_skips_draft_without_touching_github(tmp_path, monkeypatch):
    out, ev = tmp_path / "o.txt", tmp_path / "e.json"
    ev.write_text(json.dumps({"pull_request": {"number": 7, "draft": True, "head": {"sha": "abc"}}}))
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(ev))
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    gh = FakeGitHub()
    assert rb.main(request=gh) == 0
    assert "enable_claudecode=false" in out.read_text()
    assert gh.calls == []
