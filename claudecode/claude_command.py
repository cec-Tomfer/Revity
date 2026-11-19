"""Comando e ambiente con cui Revity lancia Claude Code (correzione 2).

Obiettivo: sola lettura (Read, Grep, Glob), niente shell, niente rete, niente scritture,
niente lettura di segreti; il processo non riceve GITHUB_TOKEN né altre credenziali.

NON VERIFICATO con Claude Code vero: nomi dei flag (`--tools`, `--allowed-tools`,
`--disallowed-tools`) e sintassi delle regole `Read(...)` vanno provati con la versione
fissata di Claude Code nella prova finale. Se un flag non è riconosciuto la scansione
fallisce (fallisce chiusa), non si apre.
"""

from typing import Dict, List, Mapping

ALLOWED_TOOLS = ("Read", "Grep", "Glob")

# Strumenti da negare in modo esplicito (cintura e bretelle oltre a `--tools`).
_DENIED_BASE = ("Bash", "BashOutput", "KillShell", "WebFetch", "WebSearch", "Edit", "MultiEdit",
                "Write", "NotebookEdit", "Task", "TodoWrite", "SlashCommand")

# Percorsi segreti: negare la lettura anche dentro il repository.
_DENIED_READ = ("Read(**/.env)", "Read(**/.env.*)", "Read(**/.git/**)", "Read(.git/**)",
                "Read(**/*.pem)", "Read(**/*.key)", "Read(**/*.p12)", "Read(**/.npmrc)",
                "Read(**/id_rsa)", "Read(**/id_ed25519)")

DENIED_TOOLS = _DENIED_BASE + _DENIED_READ

# Variabili passate al processo: solo quelle necessarie. Tutto il resto (GITHUB_TOKEN,
# GH_TOKEN, ACTIONS_*, chiavi cloud, NPM_TOKEN...) viene scartato.
_ENV_ALLOWLIST = ("ANTHROPIC_API_KEY", "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TERM",
                  "SHELL", "USER", "NODE_OPTIONS")


def build_command(model: str) -> List[str]:
    return [
        "claude",
        "--output-format", "json",
        "--model", model,
        "--tools", ",".join(ALLOWED_TOOLS),
        "--allowed-tools", ",".join(ALLOWED_TOOLS),
        "--disallowed-tools", ",".join(DENIED_TOOLS),
    ]


def build_env(environ: Mapping[str, str]) -> Dict[str, str]:
    return {k: environ[k] for k in _ENV_ALLOWLIST if k in environ}
