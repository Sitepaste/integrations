// Runs on Node's built-in runner with native type stripping — no test
// dependencies: `npm test` (node --test src/utils.test.ts). utils.ts is
// import-free, which is what keeps it testable outside Obsidian.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  apiErrorMessage,
  deployRefusalMessage,
  envelopeFieldErrors,
  errorDetail,
  extractOverrides,
  extractShowListings,
  normalizeSection,
  pageFieldErrors,
  pagePath,
  slugify,
  validatePage,
} from './utils.ts';

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

// --- publishedAt: what the API's RFC 3339 parse takes ---

test('a UTC timestamp is accepted, the form a date-only note is completed to', () => {
  assert.deepEqual(validatePage(page({ publishedAt: '2025-01-15T12:00:00Z' })), []);
});

test('an offset and fractional seconds are accepted', () => {
  assert.deepEqual(validatePage(page({ publishedAt: '2025-01-15T12:00:00+02:00' })), []);
  assert.deepEqual(validatePage(page({ publishedAt: '2025-01-15T12:00:00.123Z' })), []);
});

test('a timestamp with no zone is refused, because RFC 3339 requires one', () => {
  const errors = validatePage(page({ publishedAt: '2025-01-15T12:00:00' }));
  assert.equal(errors[0]?.field, 'publishedAt');
});

test('a date that is not a timestamp is refused', () => {
  // Date reads both of these; the API reads neither.
  assert.equal(validatePage(page({ publishedAt: 'January 15, 2025' }))[0]?.field, 'publishedAt');
  assert.equal(validatePage(page({ publishedAt: '2025-01-15' }))[0]?.field, 'publishedAt');
});

test('a day that does not exist is refused', () => {
  assert.equal(
    validatePage(page({ publishedAt: '2025-02-30T00:00:00Z' }))[0]?.field,
    'publishedAt',
  );
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

// --- showListings: the homepage's own setting ---

test('a homepage carries show_listings through to the payload', () => {
  const { showListings } = extractShowListings({ show_listings: true }, 'homepage');
  assert.equal(showListings, true);
});

test('an explicit off is sent rather than dropped', () => {
  // Dropping it would leave the homepage on whatever it was last set to.
  const { showListings } = extractShowListings({ show_listings: false }, 'homepage');
  assert.equal(showListings, false);
});

test('show_listings on a blog post is not a field this plugin knows', () => {
  const { showListings, errors } = extractShowListings({ show_listings: true }, 'blog');
  assert.equal(showListings, undefined);
  assert.deepEqual(errors, []);
});

test('a non-boolean show_listings on a homepage is a validation error', () => {
  const { errors } = extractShowListings({ show_listings: 'maybe' }, 'homepage');
  assert.equal(errors[0]?.field, 'show_listings');
});

// --- API errors ---
//
// Every body below is the API's own envelope: `error` is the human sentence
// and `code` the stable identifier. Reading them the other way round matches
// no code and drops every tailored message, which is a failure that shows up
// only in a user's notice — so the shapes here are what pins it.

test('a missing scope names the scope and how to fix it', () => {
  const msg = apiErrorMessage(403, {
    error: 'this token does not carry the "content" scope',
    code: 'token_scope_required',
    scope: 'content',
  });
  assert.match(msg, /"content" scope/);
  assert.match(msg, /Account > Tokens/);
});

test('a missing scope does not guess a scope the body did not name', () => {
  const msg = apiErrorMessage(403, { error: 'scope missing', code: 'token_scope_required' });
  assert.match(msg, /Account > Tokens/);
  assert.doesNotMatch(msg, /"content"/);
});

test('a past-due subscription is not reported as a missing plan', () => {
  const msg = apiErrorMessage(403, {
    error: 'your subscription is past due',
    code: 'payment_past_due',
  });
  assert.match(msg, /past due/);
  assert.doesNotMatch(msg, /Upgrade/);
});

test('a refused page setting shows what was refused, not a blanket upgrade', () => {
  const msg = apiErrorMessage(403, {
    error: "The 'wasy' theme is reserved",
    code: 'theme_restricted',
  });
  assert.equal(msg, "The 'wasy' theme is reserved.");
});

test('a plan-level 403 without a sentence still asks for Pro', () => {
  assert.match(apiErrorMessage(403, { code: 'forbidden' }), /Pro plan/);
});

test('the known statuses keep their own guidance', () => {
  assert.match(
    apiErrorMessage(401, { error: 'invalid or revoked token', code: 'unauthorized' }),
    /Invalid API key/,
  );
  assert.match(apiErrorMessage(413, {}), /too large/);
  assert.match(
    apiErrorMessage(429, { error: 'rate limit exceeded', code: 'rate_limited' }),
    /Rate limited/,
  );
});

test('an unpunctuated API sentence is closed before more text follows it', () => {
  // The API punctuates some of its own sentences and not others, so a detail
  // pasted straight in front of the next one runs the two together.
  const msg = apiErrorMessage(402, { error: 'metrics require Pro plan', code: 'plan_required' });
  assert.match(msg, /Pro plan\. Check your plan limits/);
});

test('a 402 carries the quota detail the API sent', () => {
  const msg = apiErrorMessage(402, {
    error: 'Upgrade to Pro to enable password protection.',
    code: 'plan_required',
  });
  assert.match(msg, /Upgrade to Pro to enable password protection/);
});

test('a 402 without any detail still reads as a sentence', () => {
  assert.equal(
    apiErrorMessage(402, {}),
    'Quota exceeded. Check your plan limits at sitepaste.com.',
  );
});

test('an unmapped status falls back to the sentence and status', () => {
  assert.equal(
    apiErrorMessage(500, { error: 'failed to save pages', code: 'internal_error' }),
    'Publish failed (500): failed to save pages',
  );
});

test('an empty body still produces a message', () => {
  assert.equal(apiErrorMessage(502, {}), 'Publish failed (502): unknown error');
});

// --- errorDetail: the same triple, read out of a refused deploy's envelope ---

test('a deploy refused for a missing scope names the deploy scope', () => {
  const detail = errorDetail({
    error: 'This token does not carry the "deploy" scope.',
    code: 'token_scope_required',
    scope: 'deploy',
  });
  assert.match(detail, /"deploy" scope/);
  assert.match(detail, /Account > Tokens/);
});

test('a deploy refused by a quota shows the API sentence', () => {
  assert.equal(
    errorDetail({
      error: 'The monthly build limit for your plan has been reached.',
      code: 'quota_exceeded',
    }),
    'The monthly build limit for your plan has been reached.',
  );
});

// --- deployRefusalMessage: a refused deploy always says something ---

test('a refusal with an envelope reads as the envelope does', () => {
  assert.equal(
    deployRefusalMessage(429, { error: 'deploy cooldown active', code: 'cooldown_active' }),
    'deploy cooldown active',
  );
});

test('a refusal with no envelope still says the deploy was refused', () => {
  // A proxy's HTML 502 never reaches the API, so there is no envelope to
  // render. An empty string here would report the refusal as a clean
  // publish, since the callers show this only when it is truthy.
  assert.equal(deployRefusalMessage(502, {}), 'the deploy was refused (HTTP 502)');
});

// --- Envelope field errors: the batch's own problems, belonging to no page ---

test('a problem with the batch itself is reported without a page to blame', () => {
  const errors = envelopeFieldErrors({
    error: 'validation failed',
    code: 'validation_failed',
    fields: { pages: 'pages array exceeds 5000 entries' },
  });
  assert.deepEqual(errors, [{ field: 'pages', message: 'pages array exceeds 5000 entries' }]);
});

test('a body with no envelope fields yields none, so callers need no status check', () => {
  assert.deepEqual(envelopeFieldErrors({ error: 'not found', code: 'not_found' }), []);
});

// --- Batch field errors: flattened, and tied back to the page's index ---

test('field errors keep the page index so a caller can name the file', () => {
  const errors = pageFieldErrors({
    error: 'validation failed',
    pages: { '2': { slug: 'invalid slug', title: 'title is required for new pages' } },
  });
  assert.equal(errors.length, 2);
  assert.deepEqual(
    errors.map((e) => e.index),
    [2, 2],
  );
  assert.deepEqual(errors.map((e) => e.field).sort(), ['slug', 'title']);
});

test('a body without page errors yields none, so callers need no status check', () => {
  assert.deepEqual(pageFieldErrors({ error: 'token_scope_required', scope: 'content' }), []);
  assert.deepEqual(pageFieldErrors({}), []);
});

test('a non-numeric page key comes back as -1 rather than a bad index', () => {
  const errors = pageFieldErrors({ pages: { oops: { slug: 'bad' } } });
  assert.equal(errors[0]?.index, -1);
});
