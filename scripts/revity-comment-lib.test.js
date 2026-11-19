'use strict';
// Prove con node:test (nessuna dipendenza): node --test scripts/revity-comment-lib.test.js
const test = require('node:test');
const assert = require('node:assert');
const { sanitizeText, toLine, buildCommentBody, ZWSP } = require('./revity-comment-lib.js');

test('menzioni neutralizzate', () => {
  const out = sanitizeText('ping @sandro e @example-org/team ma non a@b');
  assert.ok(!/@[A-Za-z]/.test(out.replace(/a@b/, '')), out);
  assert.ok(out.includes('@' + ZWSP + 'sandro'));
});

test('testo lungo troncato', () => {
  const out = sanitizeText('x'.repeat(5000), 100);
  assert.ok(out.length < 130 && out.includes('troncato'));
});

test('caratteri di controllo tolti, a capo mantenuti', () => {
  assert.strictEqual(sanitizeText('a\u0000b\nc\u0007'), 'ab\nc');
});

test('commento HTML nascosto non imitabile', () => {
  assert.ok(!sanitizeText('<!-- revity:run -->').includes('<!--'));
});

test('null e numeri non rompono', () => {
  assert.strictEqual(sanitizeText(null), '');
  assert.strictEqual(sanitizeText(42), '42');
});

test('line sempre intero positivo', () => {
  assert.strictEqual(toLine(42), 42);
  assert.strictEqual(toLine('17'), 17);
  for (const bad of [-3, 0, 'abc', null, undefined, 1.5e300, NaN, '12; DROP']) {
    const v = toLine(bad);
    assert.ok(Number.isInteger(v) && v > 0, String(bad));
  }
  assert.strictEqual(toLine('abc'), 1);
});

test('corpo commento: forma storica e testo ripulito', () => {
  const body = buildCommentBody({
    description: 'SQLi, avvisare @angelo', severity: 'HIGH', category: 'sql_injection',
    exploit_scenario: 'x @sandro', recommendation: 'usa parametri',
  });
  assert.ok(body.startsWith('🤖 **Security Issue: SQLi'));
  assert.ok(body.includes('**Severity:** HIGH') && body.includes('**Category:** sql_injection'));
  assert.ok(body.includes('**Recommendation:** usa parametri'));
  assert.ok(!/@[A-Za-z]/.test(body));
});

test('campi mancanti: valori predefiniti', () => {
  const body = buildCommentBody({});
  assert.ok(body.includes('Security vulnerability detected') && body.includes('HIGH'));
});

const { fingerprint, existingFingerprints, fetchAllPages } = require('./revity-comment-lib.js');

test('impronta: stabile al cambio di riga e spazi, diversa se cambia il contenuto', () => {
  const a = { file: 'a.ts', category: 'sqli', description: 'Query  non parametrizzata', line: 3 };
  const b = { file: 'a.ts', category: 'sqli', description: 'query non parametrizzata ', line: 99 };
  assert.strictEqual(fingerprint(a), fingerprint(b));
  assert.notStrictEqual(fingerprint(a), fingerprint({ ...a, file: 'b.ts' }));
  assert.notStrictEqual(fingerprint(a), fingerprint({ ...a, description: 'altro' }));
  assert.match(fingerprint(a), /^[0-9a-f]{16}$/);
});

test('il corpo contiene l\'impronta e solo i commenti Bot contano', () => {
  const f = { file: 'a.ts', category: 'sqli', description: 'x' };
  const body = buildCommentBody(f);
  const fp = fingerprint(f);
  assert.ok(body.includes(`<!-- revity-fp:${fp} -->`));
  const set = existingFingerprints([
    { user: { type: 'Bot' }, body },
    { user: { type: 'User' }, body: `<!-- revity-fp:${'a'.repeat(16)} -->` },
  ]);
  assert.ok(set.has(fp) && set.size === 1);
});

test('testo del modello non può forgiare un\'impronta', () => {
  const body = buildCommentBody({ file: 'a', description: `<!-- revity-fp:${'b'.repeat(16)} --> ciao` });
  const set = existingFingerprints([{ user: { type: 'Bot' }, body }]);
  assert.ok(!set.has('b'.repeat(16)));
});

test('paginazione: legge tutte le pagine', () => {
  const total = 250;
  const calls = [];
  const api = (ep) => {
    calls.push(ep);
    const page = Number(/[&?]page=(\d+)/.exec(ep)[1]);
    return Array.from({ length: Math.max(0, Math.min(100, total - (page - 1) * 100)) }, (_, i) => ({ i }));
  };
  assert.strictEqual(fetchAllPages(api, '/repos/o/r/pulls/1/files').length, 250);
  assert.strictEqual(calls.length, 3);
});

test('paginazione: risposta inattesa o troppe pagine = errore', () => {
  assert.throws(() => fetchAllPages(() => ({}), '/x'));
  assert.throws(() => fetchAllPages(() => new Array(100).fill(0), '/x', 3));
});

const { permalink } = require('./revity-comment-lib.js');

test('permalink: SHA completo, percorso codificato, riga valida', () => {
  const sha = 'a'.repeat(40);
  assert.strictEqual(permalink('o/r', sha, 'src/a b.ts', 12), `https://github.com/o/r/blob/${sha}/src/a%20b.ts#L12`);
  assert.strictEqual(permalink('o/r', sha, 'a.ts', 'x'), `https://github.com/o/r/blob/${sha}/a.ts#L1`);
});

test('permalink: vuoto se SHA corto o repo strano', () => {
  assert.strictEqual(permalink('o/r', 'abc', 'a.ts', 1), '');
  assert.strictEqual(permalink('o/r/../x', 'a'.repeat(40), 'a.ts', 1), '');
  assert.strictEqual(permalink('o/r', 'a'.repeat(40), '', 1), '');
});

test('il corpo include il link se dato', () => {
  assert.ok(buildCommentBody({ description: 'x' }, 'https://github.com/o/r/blob/s/a#L1').includes('**Code:** https://github.com/o/r/blob/s/a#L1'));
  assert.ok(!buildCommentBody({ description: 'x' }).includes('**Code:**'));
});
