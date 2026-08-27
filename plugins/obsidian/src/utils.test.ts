// Runs on Node's built-in runner with native type stripping — no test
// dependencies: `npm test` (node --test src/utils.test.ts). utils.ts is
// import-free, which is what keeps it testable outside Obsidian.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { extractOverrides, normalizeSection, pagePath, slugify, validatePage } from './utils.ts';

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

// --- Passthrough fields: author, password, OG image, language, overrides ---

test('author id passes through as authorId', () => {
  const { overrides, errors } = extractOverrides({ author: 'a7XkQw3mZlPwR9tGhY3nB' });
  assert.deepEqual(errors, []);
  assert.equal(overrides.authorId, 'a7XkQw3mZlPwR9tGhY3nB');
});

test('an author name is rejected — pages reference authors by id', () => {
  const { errors } = extractOverrides({ author: 'Ada Lovelace' });
  assert.equal(errors[0]?.field, 'author');
});

test('an empty author clears the field', () => {
  const { overrides, errors } = extractOverrides({ author: '' });
  assert.deepEqual(errors, []);
  assert.equal(overrides.authorId, '');
});

test('a password shorter than 8 characters is rejected', () => {
  const { errors } = extractOverrides({ password: 'short' });
  assert.equal(errors[0]?.field, 'password');
});

test('a valid password passes through, and an empty one clears', () => {
  assert.equal(
    extractOverrides({ password: 'supersecret123' }).overrides.password,
    'supersecret123',
  );
  assert.equal(extractOverrides({ password: '' }).overrides.password, '');
});

test('og_image_url accepts http(s) and /media, rejects other schemes', () => {
  assert.equal(
    extractOverrides({ og_image_url: 'https://example.com/og.png' }).overrides.ogImageUrl,
    'https://example.com/og.png',
  );
  assert.equal(extractOverrides({ og_image_url: 'ftp://x' }).errors[0]?.field, 'og_image_url');
});

test('language accepts tags like pt-BR and rejects free text', () => {
  assert.equal(extractOverrides({ language: 'pt-BR' }).overrides.language, 'pt-BR');
  assert.equal(extractOverrides({ language: 'not a language' }).errors[0]?.field, 'language');
});

test('language accepts singleton subtags and rejects overlong tags', () => {
  // 1-char singleton/private-use subtags are valid BCP-47 and the API
  // accepts them.
  assert.equal(
    extractOverrides({ language: 'de-DE-u-co-phonebk' }).overrides.language,
    'de-DE-u-co-phonebk',
  );
  // Well-formed subtags, but past the 35-character cap.
  assert.equal(
    extractOverrides({ language: 'en-abcdefgh-abcdefgh-abcdefgh-abcdefgh' }).errors[0]?.field,
    'language',
  );
});

test('font_size is restricted to the known sizes', () => {
  assert.equal(extractOverrides({ font_size: 'compact' }).overrides.fontSize, 'compact');
  assert.equal(extractOverrides({ font_size: 'enormous' }).errors[0]?.field, 'font_size');
});

test('tri-state overrides accept booleans and "inherit"', () => {
  const { overrides, errors } = extractOverrides({
    show_toc: false,
    show_comments: true,
    show_tags: 'inherit',
  });
  assert.deepEqual(errors, []);
  assert.equal(overrides.showToc, 'false');
  assert.equal(overrides.showComments, 'true');
  assert.equal(overrides.showTags, 'inherit');
});

test('an invalid tri-state value is rejected', () => {
  assert.equal(extractOverrides({ show_toc: 'sometimes' }).errors[0]?.field, 'show_toc');
});

test('absent keys stay absent so the server keeps existing values', () => {
  const { overrides } = extractOverrides({ title: 'T', draft: true });
  assert.deepEqual(overrides, {});
});
