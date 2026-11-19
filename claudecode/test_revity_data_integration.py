"""Prove di integrazione della correzione 6 sul codice esistente. Solo dati finti."""

import json
import os
from unittest.mock import Mock, patch

from claudecode.claude_api_client import ClaudeAPIClient
from claudecode.github_action_audit import GitHubActionClient


def _client():
    with patch.dict(os.environ, {'GITHUB_TOKEN': 't'}):
        return GitHubActionClient()


def test_default_exclusions_apply_without_configuration():
    c = _client()
    assert c._is_excluded('node_modules/a/b.js')
    assert c._is_excluded('.env.production')
    assert not c._is_excluded('src/api/orders.ts')


def test_diff_is_capped_and_summary_recorded():
    c = _client()
    big = "".join(
        f"diff --git a/src/f{i}.ts b/src/f{i}.ts\n--- a/src/f{i}.ts\n+++ b/src/f{i}.ts\n" + "+x\n" * 100
        for i in range(10))
    resp = Mock(text=big)
    resp.raise_for_status = Mock()
    with patch('requests.get', return_value=resp), patch.dict(os.environ, {'REVITY_MAX_DIFF_CHARS': '1500'}):
        out = c.get_pr_diff('o/r', 1)
    assert len(out) <= 1500
    assert c.last_omitted_files and c.last_diff_files
    assert out.count('diff --git') == len(c.last_diff_files)


def test_diff_drops_lockfiles_and_secrets():
    c = _client()
    diff = ("diff --git a/package-lock.json b/package-lock.json\n+x\n"
            "diff --git a/.env b/.env\n+KEY=abc\n"
            "diff --git a/src/a.ts b/src/a.ts\n+ok\n")
    resp = Mock(text=diff)
    resp.raise_for_status = Mock()
    with patch('requests.get', return_value=resp):
        out = c.get_pr_diff('o/r', 1)
    assert 'src/a.ts' in out and 'KEY=abc' not in out and 'package-lock' not in out


def test_filter_never_reads_outside_repo_even_for_hostile_finding(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    api = ClaudeAPIClient(api_key="finto")  # nessuna chiamata di rete in questo test
    with patch.dict(os.environ, {'REPO_PATH': str(repo)}):
        for hostile in ("../secret.txt", str(tmp_path / "secret.txt"), "/proc/self/environ"):
            prompt = api._generate_single_finding_prompt({'file': hostile, 'description': 'x'}, {})
            assert "TOP SECRET" not in prompt
            assert "Error reading file" in prompt
    assert api.files_read == []


def test_filter_reads_repo_file_and_records_size(tmp_path):
    (tmp_path / "a.ts").write_text("let x = 1")
    api = ClaudeAPIClient(api_key="finto")
    with patch.dict(os.environ, {'REPO_PATH': str(tmp_path)}):
        prompt = api._generate_single_finding_prompt({'file': 'a.ts'}, {})
    assert "let x = 1" in prompt
    assert api.files_read == [('a.ts', 9)]


def test_excluded_details_are_slim():
    from claudecode.github_action_audit import slim_excluded_details
    ex = [{'finding': {'file': 'a.ts', 'description': 'DESCRIZIONE LUNGA'},
           'exclusion_reason': 'x', 'filter_stage': 'hard_rules', 'justification': 'GIUST'}]
    out = json.dumps(slim_excluded_details(ex))
    assert 'GIUST' not in out and 'DESCRIZIONE' not in out and 'a.ts' in out
