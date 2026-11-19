"""Tetto di esecuzioni per PR (Revity, correzione 4).

Sostituisce il marcatore in cache (una sola esecuzione per PR). Il contatore vive in un
commento «sticky» della PR, con un marcatore nascosto:

    <!-- revity-run-counter {"n": 2, "sha": "<head sha>", "capped_notified": false} -->

Regole: a ogni nuovo commit (head sha) si incrementa; allo stesso commit non si riscansiona;
al raggiungimento del tetto (predefinito 5) non si scansiona più e il commento lo dice una
sola volta. Se il contatore non si può leggere/scrivere si NON scansiona (fail closed, nessuna
spesa fuori controllo). Solo i commenti di utenti di tipo Bot contano come contatore.

Usare `concurrency` nel workflow (un gruppo per PR) per evitare corse tra esecuzioni.
Solo libreria standard: gira prima dell'installazione delle dipendenze.
"""

import json
import os
import re
import sys
import urllib.request
from typing import Any, Callable, Dict, List, Optional

DEFAULT_MAX_RUNS = 5
MAX_ALLOWED = 50
PER_PAGE = 100
MAX_PAGES = 50
_MARKER_RE = re.compile(r"<!--\s*revity-run-counter\s+(\{.*?\})\s*-->", re.DOTALL)

Request = Callable[..., Any]


def parse_max_runs(value: Optional[str]) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_MAX_RUNS
    return n if 1 <= n <= MAX_ALLOWED else DEFAULT_MAX_RUNS


def parse_counter(body: Optional[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(body, str):
        return None
    m = _MARKER_RE.search(body)
    if not m:
        return None
    try:
        d = json.loads(m.group(1))
        n = d["n"]
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            return None
        return {"n": n, "sha": str(d.get("sha", "")), "capped_notified": bool(d.get("capped_notified", False))}
    except (ValueError, KeyError, TypeError):
        return None


def render_body(state: Dict[str, Any], max_runs: int) -> str:
    marker = json.dumps({"n": state["n"], "sha": state["sha"],
                         "capped_notified": bool(state.get("capped_notified"))}, separators=(",", ":"))
    text = f"Revity: scansione {state['n']} di {max_runs} su questa PR (ultimo commit {state['sha'][:7]})."
    if state.get("capped_notified"):
        text += (f"\n\nRaggiunto il tetto di {max_runs} scansioni: i commit successivi non vengono "
                 "scansionati da Revity.")
    return f"{text}\n\n<!-- revity-run-counter {marker} -->"


def _flag(value: Optional[str], default: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() not in ("false", "0", "no")


def skip_reason(pr_obj: Dict[str, Any], environ=os.environ) -> Optional[str]:
    """Motivo per non scansionare (e non consumare il tetto): PR chiusa, bozza o di un bot.

    Bozze e bot si possono riabilitare con REVITY_SKIP_DRAFTS / REVITY_SKIP_BOTS = false.
    """
    if pr_obj.get("state") not in (None, "open"):
        return "PR non aperta"
    if _flag(environ.get("REVITY_SKIP_DRAFTS")) and pr_obj.get("draft") is True:
        return "PR in bozza: nessuna scansione finché non è pronta"
    if _flag(environ.get("REVITY_SKIP_BOTS")) and (pr_obj.get("user") or {}).get("type") == "Bot":
        return "PR creata da un bot (es. aggiornamenti automatici): nessuna scansione"
    return None


def _list_comments(request: Request, repo: str, pr: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        batch = request("GET", f"/repos/{repo}/issues/{pr}/comments?per_page={PER_PAGE}&page={page}")
        if not isinstance(batch, list):
            raise ValueError("Risposta inattesa dall'elenco dei commenti")
        out.extend(batch)
        if len(batch) < PER_PAGE:
            return out
    raise ValueError("Troppi commenti per leggere il contatore")


def _find_counter(comments: List[Dict[str, Any]]):
    best = None
    for c in comments:
        if (c.get("user") or {}).get("type") != "Bot":
            continue
        state = parse_counter(c.get("body"))
        if state and (best is None or state["n"] > best[1]["n"]):
            best = (c, state)
    return best


def reserve_run(request: Request, repo: str, pr: int, head_sha: str, max_runs: int) -> Dict[str, Any]:
    """Decide se scansionare questo commit e aggiorna il contatore. Mai solleva: in errore enable=False."""
    try:
        found = _find_counter(_list_comments(request, repo, pr))
        comment, state = found if found else (None, {"n": 0, "sha": "", "capped_notified": False})

        if state["sha"] == head_sha and state["n"] > 0:
            return {"enable": False, "n": state["n"], "error": "",
                    "reason": f"Commit {head_sha[:7]} già scansionato: non si ripete"}

        if state["n"] >= max_runs:
            if not state["capped_notified"]:
                new = {"n": state["n"], "sha": state["sha"], "capped_notified": True}
                _write(request, repo, pr, comment, new, max_runs)
            return {"enable": False, "n": state["n"], "error": "",
                    "reason": f"Raggiunto il tetto di {max_runs} scansioni per questa PR"}

        new = {"n": state["n"] + 1, "sha": head_sha, "capped_notified": False}
        _write(request, repo, pr, comment, new, max_runs)
        return {"enable": True, "n": new["n"], "error": "",
                "reason": f"Scansione {new['n']} di {max_runs}"}
    except Exception as e:  # fail closed
        return {"enable": False, "n": 0, "error": f"{type(e).__name__}: {e}",
                "reason": "Contatore non disponibile: nessuna scansione"}


def _write(request: Request, repo: str, pr: int, comment, state, max_runs: int) -> None:
    body = {"body": render_body(state, max_runs)}
    if comment is None:
        request("POST", f"/repos/{repo}/issues/{pr}/comments", body)
    else:
        request("PATCH", f"/repos/{repo}/issues/comments/{comment['id']}", body)


def _http_request_factory(token: str) -> Request:
    def request(method: str, path: str, data: Optional[dict] = None):
        req = urllib.request.Request(
            "https://api.github.com" + path, method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode() or "null")
    return request


def main(request: Optional[Request] = None) -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    try:
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            pr_obj = json.load(f)["pull_request"]
        pr, head_sha = int(pr_obj["number"]), str(pr_obj["head"]["sha"])
    except (KeyError, OSError, ValueError, TypeError):
        print("::error::Revity: evento PR illeggibile, nessuna scansione")
        return 1
    reason = skip_reason(pr_obj, os.environ)
    if reason:
        print(f"Revity: {reason}")
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write("enable_claudecode=false\nsilence_claudecode_comments=false\n")
        return 0
    if request is None:
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            print("::error::Revity: GITHUB_TOKEN mancante, nessuna scansione")
            return 1
        request = _http_request_factory(token)

    result = reserve_run(request, repo, pr, head_sha, parse_max_runs(os.environ.get("REVITY_MAX_RUNS")))
    if result["error"]:
        print(f"::error::Revity: {result['reason']} ({result['error']})")
    else:
        print(f"Revity: {result['reason']}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"enable_claudecode={'true' if result['enable'] else 'false'}\n")
            f.write("silence_claudecode_comments=false\n")
    return 1 if result["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
