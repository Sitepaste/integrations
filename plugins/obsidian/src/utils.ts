export function slugify(name: string, keepCase = false): string {
  let result = '';
  let lastWasHyphen = true;
  for (const ch of keepCase ? name : name.toLowerCase()) {
    if (ch === "'") continue;
    const isAlphaNum =
      (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9');
    if (isAlphaNum) {
      result += ch;
      lastWasHyphen = false;
    } else if (!lastWasHyphen) {
      result += '-';
      lastWasHyphen = true;
    }
  }
  if (result.endsWith('-')) {
    result = result.slice(0, -1);
  }
  if (result.length > MAX_SLUG_LENGTH) {
    result = result.slice(0, MAX_SLUG_LENGTH);
    if (result.endsWith('-')) {
      result = result.slice(0, -1);
    }
  }
  return result;
}

/**
 * Normalize a section path per slash-separated segment, so a nested
 * standalone section ("api/builds") keeps its separator. Empty segments
 * (leading, trailing, or doubled slashes) drop out. With keepCase, typed
 * casing survives ("API/Builds"): the server lowercases it into the stored
 * slug and captures the casing as the section's display title, the same way
 * the dashboard does.
 */
export function normalizeSection(value: string, keepCase = false): string {
  return String(value)
    .split('/')
    .map((segment) => slugify(segment, keepCase))
    .filter((segment) => segment.length > 0)
    .join('/');
}

export function titleize(slug: string): string {
  return slug
    .split('-')
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

export function pagePath(contentType: string, slug: string, section?: string): string {
  // The section may carry typed casing ("API/Builds" — display intent the
  // server captures as a title); the published URL uses its lowercase slug.
  section = section?.toLowerCase();
  if (contentType === 'homepage') return '/';
  // A standalone page's section is a custom top-level path: /{section}/{slug}
  if (contentType === 'standalone') return section ? `/${section}/${slug}` : `/${slug}`;
  if (section) return `/${contentType}/${section}/${slug}`;
  return `/${contentType}/${slug}`;
}

export const MAX_SLUG_LENGTH = 100;
export const MAX_TITLE_LENGTH = 200; // bytes
export const MAX_CONTENT_LENGTH = 100_000; // bytes
export const MAX_DESCRIPTION_LENGTH = 500; // bytes
export const MAX_API_ENDPOINT_LENGTH = 200;
export const API_ENDPOINT_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];
export const MAX_TAGS_COUNT = 20;
export const MAX_TAG_LENGTH = 30;

export const VALID_CONTENT_TYPES = new Set(['docs', 'blog', 'homepage', 'standalone']);

export interface ValidationError {
  field: string;
  message: string;
}

// Optional front matter fields passed through to the API (front matter key ->
// API payload field). `author` takes an author ID from the API's
// GET /sites/{siteId}/authors; pages reference authors by ID because names
// are not unique.
// Unlike the GitHub Action, `password` IS supported here: a private vault is
// as reasonable a place to type it as the dashboard's password field, whereas
// a repository commits it into shared history.
const PASSTHROUGH_STRING_FIELDS: Record<string, string> = {
  author: 'authorId',
  password: 'password',
  og_image_url: 'ogImageUrl',
  language: 'language',
  theme: 'theme',
  primary_color: 'primaryColor',
  font_size: 'fontSize',
  code_theme_light: 'codeThemeLight',
  code_theme_dark: 'codeThemeDark',
};

// Per-page boolean theme overrides. Tri-state on the API ("true", "false",
// "inherit") so an explicit off stays distinct from inherit-from-site; front
// matter accepts booleans or the string "inherit".
const TRISTATE_FIELDS: Record<string, string> = {
  show_toc: 'showToc',
  show_social_share: 'showSocialShare',
  show_comments: 'showComments',
  show_next_prev: 'showNextPrev',
  show_newsletter_cta: 'showNewsletterCta',
  show_tags: 'showTags',
  show_dates: 'showDates',
  show_author: 'showAuthor',
  show_reading_time: 'showReadingTime',
  show_breadcrumbs: 'showBreadcrumbs',
  show_copy_markdown: 'showCopyMarkdown',
  show_gallery_download: 'showGalleryDownload',
  full_width_gallery: 'fullWidthGallery',
  masonry_gallery: 'masonryGallery',
};

const VALID_FONT_SIZES = new Set(['compact', 'comfortable', 'large']);
// Mirrors the API's language validation: a 2-3 letter primary subtag plus
// optional 1-8 char alphanumeric subtags (singletons and private use
// included), at most 35 characters.
const LANGUAGE_RE = /^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$/;
const MAX_LANGUAGE_LENGTH = 35;

/** Optional page fields keyed by API payload field name. */
export type PageOverrides = Record<string, string>;

/**
 * Extract the optional passthrough fields (author, password, OG image,
 * language, theme overrides) from front matter, validating each. Absent keys
 * stay absent so the server keeps existing values; an empty string clears.
 */
export function extractOverrides(fm: Record<string, unknown>): {
  overrides: PageOverrides;
  errors: ValidationError[];
} {
  const overrides: PageOverrides = {};
  const errors: ValidationError[] = [];

  for (const [key, apiField] of Object.entries(PASSTHROUGH_STRING_FIELDS)) {
    const raw = fm[key];
    if (raw === undefined || raw === null) continue;
    const value = String(raw).trim();
    if (key === 'author' && value && (value.includes(' ') || value.length > 40)) {
      errors.push({
        field: 'author',
        message:
          'author must be an author ID, not a name (author names are not unique); list IDs with GET /api/v1/public/sites/{siteId}/authors',
      });
    } else if (key === 'password' && value && value.length < 8) {
      errors.push({
        field: 'password',
        message: 'password must be at least 8 characters (an empty string removes the protection)',
      });
    } else if (key === 'og_image_url' && value && !/^(https?:\/\/|\/media)/.test(value)) {
      errors.push({
        field: 'og_image_url',
        message: 'og_image_url must be an http(s) URL or a /media path',
      });
    } else if (
      key === 'language' &&
      value &&
      (value.length > MAX_LANGUAGE_LENGTH || !LANGUAGE_RE.test(value))
    ) {
      errors.push({
        field: 'language',
        message: 'language must be a language tag like "en" or "pt-BR"',
      });
    } else if (key === 'font_size' && value && !VALID_FONT_SIZES.has(value)) {
      errors.push({
        field: 'font_size',
        message: 'font_size must be one of: compact, comfortable, large',
      });
    } else {
      overrides[apiField] = value;
    }
  }

  for (const [key, apiField] of Object.entries(TRISTATE_FIELDS)) {
    const raw = fm[key];
    if (raw === undefined || raw === null) continue;
    if (raw === true || raw === false) {
      overrides[apiField] = raw ? 'true' : 'false';
    } else if (typeof raw === 'string' && ['true', 'false', 'inherit'].includes(raw.trim())) {
      overrides[apiField] = raw.trim();
    } else {
      errors.push({ field: key, message: `${key} must be true, false, or "inherit"` });
    }
  }

  return { overrides, errors };
}

/**
 * Read the homepage's showListings setting from front matter.
 *
 * It is the homepage's own setting — whether recent posts and section
 * listings show below the content — and means nothing on any other page, so
 * it is read only there. On any other page it is simply not a field this
 * plugin knows, like every other key a vault carries for some other tool.
 */
export function extractShowListings(
  fm: Record<string, unknown>,
  contentType: string,
): { showListings?: boolean; errors: ValidationError[] } {
  if (contentType !== 'homepage') return { errors: [] };
  const raw = fm['show_listings'] ?? fm['showListings'];
  if (raw === undefined || raw === null) return { errors: [] };
  if (typeof raw !== 'boolean') {
    return {
      errors: [{ field: 'show_listings', message: 'show_listings must be true or false' }],
    };
  }
  return { showListings: raw, errors: [] };
}

const encoder = new TextEncoder();

export function byteLen(s: string): number {
  return encoder.encode(s).length;
}

function isValidSlug(slug: string): boolean {
  for (let i = 0; i < slug.length; i++) {
    const ch = slug[i];
    if ((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9')) continue;
    if (ch === '-' && i > 0 && i < slug.length - 1) continue;
    return false;
  }
  return true;
}

// Sections validate on their lowercase form — the slug the server stores —
// since typed casing is display intent, not part of the slug. Standalone
// sections may nest one level ("api/builds"); docs and blog spend their
// nesting level on the content-type prefix.
function isValidSection(section: string, allowNesting: boolean): boolean {
  const segments = section.toLowerCase().split('/');
  if (segments.length > (allowNesting ? 2 : 1)) return false;
  for (const segment of segments) {
    if (segment.length === 0 || segment.length > MAX_SLUG_LENGTH) return false;
    if (!isValidSlug(segment)) return false;
    if (segment.includes('--')) return false;
  }
  return true;
}

function isValidTag(tag: string): boolean {
  for (const ch of tag) {
    if ((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch === ' ' || ch === '-') continue;
    return false;
  }
  return true;
}

export function validatePage(page: {
  slug: string;
  title: string;
  content: string;
  contentType?: string;
  section?: string;
  description?: string;
  apiEndpoint?: string;
  tags?: string[];
  publishedAt?: string;
}): ValidationError[] {
  const errors: ValidationError[] = [];

  if (!page.slug) {
    errors.push({ field: 'slug', message: 'slug is required' });
  } else if (page.slug.length > MAX_SLUG_LENGTH) {
    errors.push({
      field: 'slug',
      message: `slug exceeds ${MAX_SLUG_LENGTH} character limit (${page.slug.length} chars)`,
    });
  } else if (!isValidSlug(page.slug)) {
    errors.push({
      field: 'slug',
      message:
        'slug must contain only lowercase letters, numbers, and hyphens, and must start and end with a letter or number',
    });
  }

  if (page.section) {
    if (!isValidSection(page.section, page.contentType === 'standalone')) {
      errors.push({
        field: 'section',
        message:
          page.contentType === 'standalone'
            ? 'section must be one or two slash-separated names of letters, numbers, and hyphens, each starting and ending with a letter or number, without consecutive hyphens'
            : 'section must contain only letters, numbers, and hyphens, must start and end with a letter or number, and must not contain consecutive hyphens (only standalone sections can nest)',
      });
    }
  }

  if (!page.title) {
    errors.push({ field: 'title', message: 'title is required' });
  } else {
    const titleBytes = byteLen(page.title);
    if (titleBytes > MAX_TITLE_LENGTH) {
      errors.push({
        field: 'title',
        message: `title exceeds ${MAX_TITLE_LENGTH} byte limit (${titleBytes} bytes)`,
      });
    }
  }

  const contentBytes = byteLen(page.content);
  if (contentBytes > MAX_CONTENT_LENGTH) {
    errors.push({
      field: 'content',
      message: `content exceeds ${MAX_CONTENT_LENGTH} byte limit (${contentBytes} bytes)`,
    });
  }

  if (page.description) {
    const descBytes = byteLen(page.description);
    if (descBytes > MAX_DESCRIPTION_LENGTH) {
      errors.push({
        field: 'description',
        message: `description exceeds ${MAX_DESCRIPTION_LENGTH} byte limit (${descBytes} bytes)`,
      });
    }
  }

  if (page.apiEndpoint) {
    const method = page.apiEndpoint.split(' ')[0].toUpperCase();
    if (!API_ENDPOINT_METHODS.includes(method)) {
      errors.push({
        field: 'api_endpoint',
        message: `api_endpoint must start with an HTTP method (${API_ENDPOINT_METHODS.join(', ')})`,
      });
    } else if (page.apiEndpoint.length > MAX_API_ENDPOINT_LENGTH) {
      errors.push({
        field: 'api_endpoint',
        message: `api_endpoint exceeds ${MAX_API_ENDPOINT_LENGTH} character limit (${page.apiEndpoint.length} chars)`,
      });
    }
  }

  if (page.publishedAt) {
    const d = new Date(page.publishedAt);
    if (isNaN(d.getTime())) {
      errors.push({
        field: 'publishedAt',
        message: 'invalid date format; expected ISO 8601 (e.g. 2025-01-15T12:00:00Z)',
      });
    } else {
      const roundTrip = d.toISOString().slice(0, 10);
      const input = page.publishedAt.slice(0, 10);
      if (roundTrip !== input) {
        errors.push({
          field: 'publishedAt',
          message: `date "${page.publishedAt}" is not a valid ISO 8601 date`,
        });
      }
    }
  }

  if (page.tags) {
    if (page.tags.length > MAX_TAGS_COUNT) {
      errors.push({
        field: 'tags',
        message: `too many tags (${page.tags.length}, max ${MAX_TAGS_COUNT})`,
      });
    }
    for (const tag of page.tags) {
      if (tag.length > MAX_TAG_LENGTH) {
        errors.push({
          field: 'tags',
          message: `tag "${tag}" exceeds ${MAX_TAG_LENGTH} character limit`,
        });
      } else if (!isValidTag(tag.toLowerCase())) {
        // Validated on the lowercase form the server stores; typed casing
        // ("iOS") is captured server-side as the tag's display title.
        errors.push({
          field: 'tags',
          message: `tag "${tag}" contains invalid characters (only letters, numbers, spaces, and hyphens allowed)`,
        });
      }
    }
  }

  return errors;
}

// --- API error rendering ---

/** One field error from a batch response, tied to its page's index in the request. */
export interface PageFieldError {
  index: number;
  field: string;
  message: string;
}

/**
 * The detail as a finished sentence. The API punctuates some of its own error
 * sentences and not others ("Storage quota exceeded." beside "metrics require
 * Pro plan"), so anything that puts words after one has to close it first.
 */
function asSentence(detail: string): string {
  return /[.!?]$/.test(detail) ? detail : `${detail}.`;
}

/**
 * Render the API's error triple as one sentence for the user.
 *
 * The envelope is `{error, code}`: `error` is the human sentence to show and
 * `code` is the stable identifier to branch on. The batch's `build` field
 * carries the same keys, deliberately, so a refused deploy reads the
 * same whether it came back nested in a 200 or as the whole response — which
 * is why this renders the triple and the caller supplies the context.
 *
 * A missing scope gets its own sentence. The API's own wording names the
 * scope but not the remedy, and the remedy is the part that matters: scopes
 * are fixed when a token is minted, so the fix is a new token rather than an
 * edit to this one.
 */
export function errorDetail(body: Record<string, unknown>): string {
  const code = typeof body['code'] === 'string' ? body['code'] : '';
  const detail = typeof body['error'] === 'string' ? body['error'] : '';

  if (code === 'token_scope_required') {
    const scope = typeof body['scope'] === 'string' ? body['scope'] : '';
    const missing = scope ? `the "${scope}" scope` : 'a scope this request needs';
    return `This token is missing ${missing}. Token scopes are fixed at creation, so create a new token that has it under Account > Tokens.`;
  }
  if (code === 'payment_past_due') {
    return 'Your Sitepaste subscription is past due. Publishing resumes once billing is up to date.';
  }
  return detail;
}

/**
 * The user-facing headline for an API error response. It lives here rather
 * than in main.ts so it can be unit-tested without Obsidian.
 *
 * 403 is deliberately not one message. The API answers it for a token that is
 * missing the route's scope, a past-due subscription, a page setting that is
 * reserved, and a workspace that is not on Pro. Telling a Pro user with a
 * media-only token to upgrade their plan hides the real cause and the remedy,
 * so the machine code decides, not the status alone.
 */
export function apiErrorMessage(status: number, body: Record<string, unknown>): string {
  const code = typeof body['code'] === 'string' ? body['code'] : '';
  const detail = errorDetail(body);

  // The codes errorDetail answers with a remedy of their own outrank the
  // status: which of the several things a 403 means is exactly what the
  // status cannot say.
  if (code === 'token_scope_required' || code === 'payment_past_due') return detail;

  switch (status) {
    case 401:
      return 'Invalid API key. Check your key in Settings > Sitepaste.';
    case 402:
      return detail
        ? `Quota exceeded: ${asSentence(detail)} Check your plan limits at sitepaste.com.`
        : 'Quota exceeded. Check your plan limits at sitepaste.com.';
    case 403:
      // A refused page setting (a reserved theme, say) says what was refused,
      // and naming it beats a blanket "upgrade".
      return detail
        ? asSentence(detail)
        : 'API access requires a Pro plan. Upgrade at sitepaste.com.';
    case 413:
      return 'Request too large. Try publishing a smaller folder or fewer files at once.';
    case 429:
      return 'Rate limited. Wait a moment and try again.';
    default:
      return `Publish failed (${status}): ${detail || code || 'unknown error'}`;
  }
}

/**
 * The envelope's own field problems, which a 422 reports in `fields` rather
 * than keyed by entry index: a problem with the batch itself has one place to
 * point at. Empty for every other response shape, so callers need no status
 * check here either.
 */
export function envelopeFieldErrors(body: Record<string, unknown>): ValidationError[] {
  const raw = body['fields'];
  if (typeof raw !== 'object' || raw === null) return [];
  return Object.entries(raw as Record<string, unknown>).map(([field, message]) => ({
    field,
    message: String(message),
  }));
}

/**
 * The per-page field errors a 422 batch response carries, flattened and kept
 * with the page's index in the request so a caller holding the batch can name
 * the file. Empty for every other response shape, which is what lets callers
 * skip a status check. An index that is not a number comes back as -1.
 */
export function pageFieldErrors(body: Record<string, unknown>): PageFieldError[] {
  const raw = body['pages'];
  if (typeof raw !== 'object' || raw === null) return [];

  const errors: PageFieldError[] = [];
  for (const [key, fields] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof fields !== 'object' || fields === null) continue;
    const parsed = Number.parseInt(key, 10);
    const index = Number.isInteger(parsed) ? parsed : -1;
    for (const [field, message] of Object.entries(fields as Record<string, unknown>)) {
      errors.push({ index, field, message: String(message) });
    }
  }
  return errors;
}
