"""Prove automatiche per la correzione 5 (modello scelto da noi). Solo dati finti, nessuna rete."""

import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from claudecode.claude_api_client import ClaudeAPIClient
from claudecode.constants import require_model
from claudecode.findings_filter import FindingsFilter
from claudecode.github_action_audit import SimpleClaudeRunner


def test_no_hardcoded_model_names_left():
    root = Path(__file__).parent
    for name in ("constants.py", "claude_api_client.py", "findings_filter.py", "github_action_audit.py"):
        text = (root / name).read_text()
        assert "claude-opus" not in text and "claude-3-5-haiku" not in text, name


def test_require_model(monkeypatch):
    monkeypatch.delenv('CLAUDE_MODEL', raising=False)
    with pytest.raises(ValueError, match="claude-model"):
        require_model()
    with pytest.raises(ValueError):
        require_model("   ")
    assert require_model("m1") == "m1"
    monkeypatch.setenv('CLAUDE_MODEL', 'dall-env')
    assert require_model() == 'dall-env'
    assert require_model("esplicito") == "esplicito"


def test_runner_passes_chosen_model_to_cli():
    runner = SimpleClaudeRunner(model="mio-modello")
    with patch('subprocess.run') as run, patch('pathlib.Path.exists', return_value=True):
        run.return_value = Mock(returncode=0, stdout='{"result": "{\\"findings\\": []}"}', stderr='')
        ok, err, _ = runner.run_security_audit(Path('/tmp/x'), 'p')
    assert ok, err
    cmd = run.call_args[0][0]
    assert cmd[cmd.index('--model') + 1] == "mio-modello"


def test_runner_without_model_fails_without_launching_claude(monkeypatch):
    monkeypatch.delenv('CLAUDE_MODEL', raising=False)
    runner = SimpleClaudeRunner()
    with patch('subprocess.run') as run, patch('pathlib.Path.exists', return_value=True):
        ok, err, _ = runner.run_security_audit(Path('/tmp/x'), 'p')
    assert not ok and "Modello non configurato" in err
    run.assert_not_called()


def test_api_client_requires_model(monkeypatch):
    monkeypatch.delenv('CLAUDE_MODEL', raising=False)
    with pytest.raises(ValueError):
        ClaudeAPIClient(api_key="finto")


def test_api_client_has_no_connection_test():
    assert not hasattr(ClaudeAPIClient, 'validate_api_access')


def test_filter_creation_makes_no_network_call():
    with patch('claudecode.claude_api_client.Anthropic') as anth:
        f = FindingsFilter(use_claude_filtering=True, api_key="finto", model="m")
    assert f.use_claude_filtering and f.claude_client is not None
    anth.return_value.messages.create.assert_not_called()


def test_filter_without_model_raises_instead_of_silently_disabling(monkeypatch):
    monkeypatch.delenv('CLAUDE_MODEL', raising=False)
    with pytest.raises(ValueError):
        FindingsFilter(use_claude_filtering=True, api_key="finto")


def test_filter_api_errors_are_counted_and_visible():
    with patch('claudecode.claude_api_client.Anthropic'):
        f = FindingsFilter(use_claude_filtering=True, api_key="finto", model="m")
    f.claude_client.analyze_single_finding = Mock(return_value=(False, {}, "boom"))
    ok, res, stats = f.filter_findings([{'file': 'a.ts', 'description': 'SQL injection', 'severity': 'HIGH'}])
    assert ok and stats.api_errors == 1
    assert res['analysis_summary']['api_errors'] == 1


def test_main_stops_with_config_error_when_model_missing(monkeypatch, capsys):
    from claudecode import github_action_audit as g
    monkeypatch.delenv('CLAUDE_MODEL', raising=False)
    monkeypatch.setenv('GITHUB_REPOSITORY', 'o/r')
    monkeypatch.setenv('PR_NUMBER', '1')
    with patch('requests.get') as get, pytest.raises(SystemExit) as e:
        g.main()
    assert e.value.code == 2
    assert "claude-model" in json.loads(capsys.readouterr().out)['error']
    get.assert_not_called()
