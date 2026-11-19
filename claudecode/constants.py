"""
Constants and configuration values for ClaudeCode.
"""

import os

# API Configuration
# Revity: nessun modello predefinito. Il modello lo sceglie chi configura il workflow
# (input `claude-model`, variabile CLAUDE_MODEL). Se manca, la scansione si ferma con un errore.
DEFAULT_CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL') or ''


def require_model(value=None) -> str:
    """Ritorna il nome del modello o solleva ValueError se non è configurato."""
    model = (value or os.environ.get('CLAUDE_MODEL') or '').strip()
    if not model:
        raise ValueError("Modello non configurato: imposta l'input 'claude-model' (CLAUDE_MODEL)")
    return model

DEFAULT_TIMEOUT_SECONDS = 180  # 3 minutes
DEFAULT_MAX_RETRIES = 3
RATE_LIMIT_BACKOFF_MAX = 30  # Maximum backoff time for rate limits

# Token Limits
PROMPT_TOKEN_LIMIT = 16384  # 16k tokens max per risposta

# Exit Codes
EXIT_SUCCESS = 0
EXIT_GENERAL_ERROR = 1
EXIT_CONFIGURATION_ERROR = 2

# Subprocess Configuration
SUBPROCESS_TIMEOUT = 1200  # 20 minutes for Claude Code execution

