// Runs on Node's built-in runner with native type stripping — no test
// dependencies: `npm test` (node --test src/utils.test.ts). utils.ts is
// import-free, which is what keeps it testable outside Obsidian.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeSection, pagePath, slugify, validatePage } from './utils.ts';

const page = (overrides: Record<string, unknown>) => ({
  slug: 'post-builds',
  title: 'POST /builds',
  content: 'body',
  ...overrides,
});

// --- Section shape: nesting mirrors the server's rules ---

test('a standalone page may use a nested section', () => {
  assert.deepEqual(validatePage(page({ contentType: 'standalone', section: 'api/builds' })), []);
});

test('a docs page may not use a nested section', () => {
  const errors = validatePage(page({ contentType: 'docs', section: 'guides/advanced' }));
  assert.equal(errors.length, 1, 'nested docs section should produce exactly one section error');
  assert.equal(errors[0].field, 'section');
});

test('a standalone section may not nest deeper than one level', () => {
  const errors = validatePage(page({ contentType: 'standalone', section: 'a/b/c' }));
  assert.equal(errors[0]?.field, 'section');
});

// --- Casing: typed casing is sent to the server, validated on its slug ---

test('a cased section value is valid — casing is display intent, not slug', () => {
  assert.deepEqual(validatePage(page({ contentType: 'standalone', section: 'API/Builds' })), []);
});

test('a cased tag is valid — "iOS" is stored as "ios" with its casing as title', () => {
  assert.deepEqual(validatePage(page({ tags: ['iOS', 'My Tag'] })), []);
});

test('invalid tag characters are rejected regardless of casing', () => {
  const errors = validatePage(page({ tags: ['C++'] }));
  assert.equal(errors[0]?.field, 'tags');
});

// --- normalizeSection: what front matter becomes on the wire ---

test('normalizeSection keeps one slash for nesting and drops empty segments', () => {
  assert.equal(normalizeSection('api/builds'), 'api/builds');
  assert.equal(normalizeSection('/api//builds/'), 'api/builds');
});

test('normalizeSection with keepCase preserves typed casing per segment', () => {
  assert.equal(normalizeSection('API/Post Builds', true), 'API/Post-Builds');
});

test('pagePath renders the published URL, not the typed section casing', () => {
  // A cased section publishes at its lowercase slug — the notice a user
  // clicks through must show the URL that actually exists.
  assert.equal(pagePath('standalone', 'post-builds', 'API/Builds'), '/api/builds/post-builds');
});

test('slugify still lowercases by default', () => {
  // Called on note basenames (extension already stripped by Obsidian).
  assert.equal(slugify('Hello World'), 'hello-world');
});
