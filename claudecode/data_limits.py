"""Limiti ai dati inviati ad Anthropic (Revity, correzione 6).

- esclusioni predefinite di cartelle e file (dipendenze, build, blocchi, segreti, binari);
- tetto alla dimensione del diff, tagliato sempre sul confine tra file (mai a metà);
- lettura dei file per il filtro solo dentro la cartella del repository, con tetto in byte;
- riepilogo di cosa viene inviato (nomi e dimensioni, mai il contenuto).
"""

import fnmatch
import os
import re
from pathlib import Path, PurePosixPath
from typing import List, Optional, Sequence, Tuple

DEFAULT_MAX_DIFF_CHARS = 200_000
DEFAULT_MAX_FILE_BYTES = 100_000

EXCLUDED_DIR_NAMES = frozenset({
    "node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage", "vendor",
    "__pycache__", ".venv", "venv", ".medusa", ".cache", ".turbo",
})

# Segreti: non vanno mai letti né inviati.
SENSITIVE_FILE_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks",
                           "id_rsa", "id_ed25519", "*.keystore", ".npmrc", ".netrc")

# Escluso dal diff (rumore, generati, binari) ma non necessariamente segreto.
NOISE_FILE_PATTERNS = ("*.lock", "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "*.min.js",
                       "*.min.css", "*.map", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg",
                       "*.ico", "*.webp", "*.pdf", "*.woff", "*.woff2", "*.ttf", "*.zip",
                       "*.gz", "*.mp4")


def _parts(path: str) -> List[str]:
    return [p for p in PurePosixPath(path.replace("\\", "/")).parts if p not in ("", ".", "/")]


def _matches(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(name.lower(), p.lower()) for p in patterns)


def is_sensitive_path(path: str) -> bool:
    parts = _parts(path)
    if not parts:
        return False
    if ".git" in parts[:-1] or parts[-1] == ".git":
        return True
    return _matches(parts[-1], SENSITIVE_FILE_PATTERNS)


def is_default_excluded(path: str) -> bool:
    parts = _parts(path)
    if not parts:
        return False
    if any(p in EXCLUDED_DIR_NAMES for p in parts[:-1]):
        return True
    return is_sensitive_path(path) or _matches(parts[-1], NOISE_FILE_PATTERNS)


def _positive_int(value, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return v if v > 0 else default


def limit_diff(diff_text: str, max_chars: Optional[int] = None) -> Tuple[str, List[str], List[str]]:
    """Tiene solo sezioni di file intere fino a max_chars.

    Ritorna (diff_limitato, file_tenuti, file_omessi). Se max_chars non è un intero
    positivo si usa il valore predefinito (mai «senza limite»).
    """
    limit = _positive_int(max_chars, DEFAULT_MAX_DIFF_CHARS)
    sections = [s for s in re.split(r"(?=^diff --git )", diff_text, flags=re.MULTILINE) if s]
    kept_text: List[str] = []
    kept: List[str] = []
    omitted: List[str] = []
    used = 0
    for s in sections:
        m = re.match(r"diff --git a/(.*?) b/", s)
        name = m.group(1) if m else "(sconosciuto)"
        if used + len(s) <= limit:
            kept_text.append(s)
            kept.append(name)
            used += len(s)
        else:
            omitted.append(name)
    return "".join(kept_text), kept, omitted


def read_repo_file(repo_root: str, file_path: str, max_bytes: Optional[int] = None
                   ) -> Tuple[bool, str, str, int]:
    """Legge un file solo se sta dentro repo_root (anche dopo aver risolto i simlink).

    Ritorna (ok, contenuto, errore, byte_letti). Percorsi assoluti, con `..`, vuoti,
    segreti (.env, chiavi, .git) sono rifiutati.
    """
    limit = _positive_int(max_bytes, DEFAULT_MAX_FILE_BYTES)
    if not file_path or not isinstance(file_path, str):
        return False, "", "Percorso vuoto", 0
    if "\x00" in file_path:
        return False, "", "Percorso non valido", 0
    p = Path(file_path)
    if p.is_absolute() or file_path.startswith("~") or ".." in _parts(file_path):
        return False, "", "Percorso fuori dal repository rifiutato", 0
    if is_sensitive_path(file_path):
        return False, "", "File sensibile: non letto", 0
    try:
        root = Path(repo_root).resolve()
        target = (root / p).resolve()
        target.relative_to(root)
    except (ValueError, OSError):
        return False, "", "Percorso fuori dal repository rifiutato", 0
    if is_sensitive_path(str(target.relative_to(root))):
        return False, "", "File sensibile: non letto", 0
    try:
        if not target.is_file():
            return False, "", "File non trovato o non è un file", 0
        with open(target, "rb") as f:
            raw = f.read(limit + 1)
    except OSError as e:
        return False, "", f"Errore di lettura: {type(e).__name__}", 0
    truncated = len(raw) > limit
    raw = raw[:limit]
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += f"\n[... troncato a {limit} byte da Revity ...]"
    return True, text, "", len(raw)


def send_summary(prompt_bytes: int, diff_files: Sequence[str], omitted_files: Sequence[str],
                 filter_reads: Sequence[Tuple[str, int]]) -> str:
    """Testo per il log: cosa è stato inviato ad Anthropic (nomi e byte, non contenuti)."""
    lines = [f"[Revity] Inviato ad Anthropic: prompt di {prompt_bytes} byte",
             f"[Revity] File nel diff inviato ({len(diff_files)}): "
             + (", ".join(diff_files) if diff_files else "nessuno")]
    if omitted_files:
        lines.append(f"[Revity] File omessi dal diff per il tetto ({len(omitted_files)}): "
                     + ", ".join(omitted_files))
    if filter_reads:
        lines.append("[Revity] File letti dal filtro: "
                     + ", ".join(f"{n} ({b} byte)" for n, b in filter_reads))
    return "\n".join(lines)
