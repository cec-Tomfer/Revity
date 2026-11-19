"""Impostazioni comuni delle prove: nessuna chiave vera, modello finto (Revity non ha modello predefinito)."""

import pytest


@pytest.fixture(autouse=True)
def _modello_finto(monkeypatch):
    monkeypatch.setenv('CLAUDE_MODEL', 'claude-test-model')
