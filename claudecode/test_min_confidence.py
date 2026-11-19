"""Soglia minima di confidenza (idea ripresa in forma originale dal plugin code-review)."""

from unittest.mock import Mock

from claudecode.github_action_audit import (
    apply_findings_filter, parse_min_confidence, split_by_confidence)


def test_parse():
    assert parse_min_confidence(None) == 0.8
    assert parse_min_confidence("0.9") == 0.9
    for bad in ("abc", "2", "-1", ""):
        assert parse_min_confidence(bad) == 0.8


def test_split():
    fs = [{'confidence': 0.95}, {'confidence': 0.5}, {'confidence': 0.8}, {}, {'confidence': 'alta'}, {'confidence': True}]
    kept, low = split_by_confidence(fs, 0.8)
    assert low == [{'confidence': 0.5}]
    assert len(kept) == 5


def test_apply_filter_drops_low_confidence_and_records_it(monkeypatch):
    monkeypatch.delenv('REVITY_MIN_CONFIDENCE', raising=False)
    flt = Mock()
    findings = [{'file': 'a.ts', 'confidence': 0.9}, {'file': 'b.ts', 'confidence': 0.4}]
    flt.filter_findings.return_value = (True, {'filtered_findings': findings, 'excluded_findings': [],
                                               'analysis_summary': {}}, None)
    client = Mock()
    client._is_excluded.return_value = False
    kept, excluded, _ = apply_findings_filter(flt, findings, {}, client)
    assert [f['file'] for f in kept] == ['a.ts']
    assert excluded[0]['filter_stage'] == 'min_confidence'
