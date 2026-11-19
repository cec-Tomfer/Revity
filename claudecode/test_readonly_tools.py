"""Prove automatiche per la correzione 2 (Claude Code in sola lettura, ambiente ripulito).

ATTENZIONE: queste prove controllano solo i comandi e l'ambiente che Revity PASSA a `claude`
(con subprocess simulato). NON dimostrano che Claude Code rispetti davvero i flag:
quello resta NON VERIFICATO fino alla prova con Claude Code vero.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from claudecode.claude_command import ALLOWED_TOOLS, DENIED_TOOLS, build_command, build_env
from claudecode.github_action_audit import SimpleClaudeRunner

FORBIDDEN_IN_ALLOWED = ("Bash", "WebFetch", "WebSearch", "Edit", "Write", "NotebookEdit", "Task", "MultiEdit")


def _flag_value(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_only_read_grep_glob_allowed():
    cmd = build_command("m")
    assert ALLOWED_TOOLS == ("Read", "Grep", "Glob")
    for flag in ("--tools", "--allowed-tools"):
        assert _flag_value(cmd, flag).split(",") == ["Read", "Grep", "Glob"]


def test_dangerous_tools_are_denied_explicitly():
    denied = _flag_value(build_command("m"), "--disallowed-tools").split(",")
    for tool in FORBIDDEN_IN_ALLOWED:
        assert tool in denied, tool
    for tool in FORBIDDEN_IN_ALLOWED:
        assert tool not in ALLOWED_TOOLS


def test_secret_paths_are_denied_for_reading():
    denied = _flag_value(build_command("m"), "--disallowed-tools")
    for needle in (".env", ".git", ".pem", ".key"):
        assert needle in denied, needle


def test_model_and_json_output_kept():
    cmd = build_command("mio-modello")
    assert cmd[0] == "claude"
    assert _flag_value(cmd, "--model") == "mio-modello"
    assert _flag_value(cmd, "--output-format") == "json"


def test_env_has_no_github_token_and_keeps_api_key():
    env = build_env({
        "GITHUB_TOKEN": "ghs_FINTO", "ACTIONS_RUNTIME_TOKEN": "x", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "y",
        "ANTHROPIC_API_KEY": "sk-finta", "PATH": "/usr/bin", "HOME": "/home/r", "LANG": "C.UTF-8",
        "AWS_SECRET_ACCESS_KEY": "z", "NPM_TOKEN": "n", "GH_TOKEN": "g", "RANDOM_VAR": "1",
    })
    assert env["ANTHROPIC_API_KEY"] == "sk-finta"
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/home/r"
    for secret in ("GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
                   "AWS_SECRET_ACCESS_KEY", "NPM_TOKEN", "RANDOM_VAR"):
        assert secret not in env, secret


def test_env_without_api_key_still_builds():
    assert "ANTHROPIC_API_KEY" not in build_env({"PATH": "/usr/bin"})


def test_runner_launches_claude_with_restricted_command_and_clean_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_FINTO")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-finta")
    runner = SimpleClaudeRunner(model="m")
    with patch("subprocess.run") as run, patch("pathlib.Path.exists", return_value=True):
        run.return_value = Mock(returncode=0, stdout='{"result": "{\\"findings\\": []}"}', stderr="")
        ok, err, _ = runner.run_security_audit(Path("/tmp/x"), "p")
    assert ok, err
    cmd = run.call_args[0][0]
    assert cmd == build_command("m")
    env = run.call_args[1]["env"]
    assert "GITHUB_TOKEN" not in env and env["ANTHROPIC_API_KEY"] == "sk-finta"
    assert run.call_args[1]["input"] == "p"
