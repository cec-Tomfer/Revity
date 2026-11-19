"""Controllo dell'evento e dell'origine della PR (Revity, correzione 3).

Rifiuta in modo esplicito (errore visibile, nessuna chiamata a servizi esterni):
- eventi diversi da `pull_request` (compreso `pull_request_target`);
- PR il cui repository di origine è diverso dalla base (fork) o è stato cancellato.

I dati arrivano dal file evento scritto da GitHub (GITHUB_EVENT_PATH), non da input di testo.
Eseguibile da solo: `python -I claudecode/event_guard.py` (codice di uscita 3 se rifiutato).
"""

import json
import os
import sys
from typing import Optional, Tuple

EXIT_REFUSED = 3


def check_event(event_name: Optional[str], event_path: Optional[str],
                github_repository: Optional[str]) -> Tuple[bool, str]:
    """Ritorna (accettato, messaggio)."""
    if event_name != "pull_request":
        return False, (f"Evento '{event_name or ''}' non supportato: Revity gira solo su "
                       "'pull_request' (mai su 'pull_request_target')")
    if not event_path:
        return False, "Percorso del file evento mancante (GITHUB_EVENT_PATH)"
    try:
        with open(event_path, "r", encoding="utf-8") as f:
            event = json.load(f)
        pr = event["pull_request"]
        base_name = pr["base"]["repo"]["full_name"]
        head_repo = pr["head"].get("repo")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        return False, f"File evento illeggibile o incompleto: {type(e).__name__}"

    if not head_repo or not isinstance(head_repo, dict) or not head_repo.get("full_name"):
        return False, "Repository di origine della PR assente (fork cancellato): PR rifiutata"
    if head_repo.get("fork") is True or head_repo["full_name"].lower() != str(base_name).lower():
        return False, "PR da un repository diverso dalla base (fork): PR rifiutata"
    if not github_repository or str(base_name).lower() != github_repository.lower():
        return False, "Il repository base della PR non coincide con GITHUB_REPOSITORY: PR rifiutata"
    return True, "ok"


def main() -> int:
    ok, msg = check_event(os.environ.get("GITHUB_EVENT_NAME"),
                          os.environ.get("GITHUB_EVENT_PATH"),
                          os.environ.get("GITHUB_REPOSITORY"))
    if not ok:
        print(f"::error::Revity: {msg}")
        return EXIT_REFUSED
    print("Revity: evento e origine della PR verificati")
    return 0


if __name__ == "__main__":
    sys.exit(main())
