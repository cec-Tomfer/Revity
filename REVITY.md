# Revity

Copia modificata di [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) (licenza MIT, vedi `LICENSE`; basata sul commit `0c6a49f`). Non è un fork da tenere allineato.

Modifiche rispetto all'originale:

1. Versioni fissate (azioni per SHA, Claude Code, dipendenze con hash in `claudecode/requirements.lock`).
2. Claude Code con soli `Read`, `Grep`, `Glob`, ambiente ripulito (senza `GITHUB_TOKEN`). **Non verificato con Claude Code vero.**
3. Rifiuto esplicito di `pull_request_target` e delle PR da fork (`claudecode/event_guard.py`).
4. Una scansione per ogni nuovo commit, con tetto per PR (`claudecode/run_budget.py`, input `max-runs-per-pr`, predefinito 5); commenti solo per segnalazioni nuove.
5. Modello scelto da chi configura (`claude-model` obbligatorio); tolta la prova con modello fisso.
6. Meno dati verso Anthropic (`claudecode/data_limits.py`): esclusioni, tetti, lettura solo dentro il repository, riepilogo nel log.
7. Prove automatiche: `python -m pytest claudecode` e `node --test scripts/revity-comment-lib.test.js`.
8. Commenti con testo ripulito (`scripts/revity-comment-lib.js`), artefatti disattivati di default.

Esempio di workflow: `examples/revity-workflow.yml`. Nessuna chiave è inclusa: la chiave API va solo nei segreti del repository che usa l'azione.

## Idee riprese dal plugin «code-review» (marketplace Claude), in forma originale

Dalla pagina descrittiva del plugin (nessun codice o prompt copiato: la pagina non indica la licenza e non mostra i prompt) sono state riprese tre idee, riscritte da zero:

- salto di PR chiuse, in bozza o create da bot, senza consumare il tetto (`REVITY_SKIP_DRAFTS`, `REVITY_SKIP_BOTS`);
- soglia minima di confidenza sulle segnalazioni (`REVITY_MIN_CONFIDENCE`, predefinita 0.8; segnalazioni senza punteggio restano);
- link permanente al codice (SHA completo + riga) nei commenti.

Non riprese: i cinque agenti paralleli (conformità a CLAUDE.md, cronologia git, commenti vecchi) perché sono una revisione di qualità, non di sicurezza, e moltiplicano la spesa.
