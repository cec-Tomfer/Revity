'use strict';

/**
 * Revity — funzioni pure per i commenti sulle PR (correzione 8).
 * Il testo delle segnalazioni arriva dal modello, quindi è non fidato.
 */

const ZWSP = '​';

/** Neutralizza @menzioni (che notificano persone), toglie caratteri di controllo, limita la lunghezza. */
function sanitizeText(value, maxLen = 1500) {
  let text = typeof value === 'string' ? value : (value == null ? '' : String(value));
  // caratteri di controllo (tranne a capo e tab)
  text = text.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '');
  // @utente e @org/team -> @<ZWSP>utente: nessuna notifica
  text = text.replace(/@(?=[A-Za-z0-9_-])/g, '@' + ZWSP);
  // commenti HTML nascosti non devono poter imitare i marcatori di Revity
  text = text.replace(/<!--/g, '<!' + ZWSP + '--');
  if (text.length > maxLen) {
    text = text.slice(0, maxLen) + '… [troncato]';
  }
  return text;
}

/** Numero di riga come intero positivo; altrimenti 1 (comportamento storico). */
function toLine(value) {
  const n = typeof value === 'number' ? value : parseInt(value, 10);
  return Number.isSafeInteger(n) && n > 0 ? n : 1;
}

/** Corpo del commento: stessa forma di prima, con testo ripulito. */
/** Link permanente al codice (SHA completo del commit + riga). Vuoto se mancano i dati. */
function permalink(repo, sha, path, line) {
  if (!repo || !/^[0-9a-f]{40}$/.test(sha || '') || !path || !/^[\w.-]+\/[\w.-]+$/.test(repo)) return '';
  const encoded = String(path).split('/').map(encodeURIComponent).join('/');
  return `https://github.com/${repo}/blob/${sha}/${encoded}#L${toLine(line)}`;
}

function buildCommentBody(finding, link) {
  const message = sanitizeText(
    finding.description || (finding.extra && finding.extra.message) || 'Security vulnerability detected', 500);
  const severity = sanitizeText(finding.severity || 'HIGH', 20);
  const category = sanitizeText(finding.category || 'security_issue', 60);
  let body = `🤖 **Security Issue: ${message}**\n\n`;
  body += `**Severity:** ${severity}\n`;
  body += `**Category:** ${category}\n`;
  body += `**Tool:** ClaudeCode AI Security Analysis\n`;
  const exploit = finding.exploit_scenario ||
    (finding.extra && finding.extra.metadata && finding.extra.metadata.exploit_scenario);
  if (exploit) body += `\n**Exploit Scenario:** ${sanitizeText(exploit)}\n`;
  const rec = finding.recommendation ||
    (finding.extra && finding.extra.metadata && finding.extra.metadata.recommendation);
  if (rec) body += `\n**Recommendation:** ${sanitizeText(rec)}\n`;
  if (link) body += `\n**Code:** ${link}\n`;
  body += `\n<!-- revity-fp:${fingerprint(finding)} -->`;
  return body;
}

const crypto = require('crypto');

/** Impronta stabile di una segnalazione: file + categoria + descrizione normalizzata (non la riga). */
function fingerprint(finding) {
  const file = String(finding.file || finding.path || '');
  const category = String(finding.category || '');
  const desc = String(finding.description || (finding.extra && finding.extra.message) || '')
    .toLowerCase().replace(/\s+/g, ' ').trim();
  return crypto.createHash('sha256').update([file, category, desc].join('\u0000')).digest('hex').slice(0, 16);
}

const FP_RE = /<!-- revity-fp:([0-9a-f]{16}) -->/g;

/** Impronte già presenti nei commenti di un bot (solo utenti di tipo Bot). */
function existingFingerprints(comments) {
  const set = new Set();
  for (const c of comments || []) {
    if (!c || !c.user || c.user.type !== 'Bot' || typeof c.body !== 'string') continue;
    for (const m of c.body.matchAll(FP_RE)) set.add(m[1]);
  }
  return set;
}

/** Legge tutte le pagine di un elenco (100 per pagina) con la funzione ghApi indicata. */
function fetchAllPages(ghApi, endpoint, maxPages = 50) {
  const all = [];
  const sep = endpoint.includes('?') ? '&' : '?';
  for (let page = 1; page <= maxPages; page++) {
    const batch = ghApi(`${endpoint}${sep}per_page=100&page=${page}`);
    if (!Array.isArray(batch)) throw new Error('Unexpected response while listing ' + endpoint);
    all.push(...batch);
    if (batch.length < 100) return all;
  }
  throw new Error('Too many pages while listing ' + endpoint);
}

module.exports = { permalink, sanitizeText, toLine, buildCommentBody, fingerprint, existingFingerprints, fetchAllPages, ZWSP };
