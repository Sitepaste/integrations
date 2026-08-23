export function slugify(name: string): string {
  let result = '';
  let lastWasHyphen = true;
  for (const ch of name.toLowerCase()) {
    if (ch === "'") continue;
    const isAlphaNum = (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9');
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

export function titleize(slug: string): string {
  return slug
    .split('-')
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

export function pagePath(contentType: string, slug: string, section?: string): string {
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
export const MAX_TAGS_COUNT = 20;
export const MAX_TAG_LENGTH = 30;

export const VALID_CONTENT_TYPES = new Set(['docs', 'blog', 'homepage', 'standalone']);

export interface ValidationError {
  field: string;
  message: string;
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

function isValidSection(section: string): boolean {
  if (!isValidSlug(section)) return false;
  return !section.includes('--');
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
  section?: string;
  description?: string;
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
    if (page.section.length > MAX_SLUG_LENGTH) {
      errors.push({
        field: 'section',
        message: `section exceeds ${MAX_SLUG_LENGTH} character limit (${page.section.length} chars)`,
      });
    } else if (!isValidSection(page.section)) {
      errors.push({
        field: 'section',
        message:
          'section must contain only lowercase letters, numbers, and hyphens, must start and end with a letter or number, and must not contain consecutive hyphens',
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
      } else if (!isValidTag(tag)) {
        errors.push({
          field: 'tags',
          message: `tag "${tag}" contains invalid characters (only lowercase letters, numbers, spaces, and hyphens allowed)`,
        });
      }
    }
  }

  return errors;
}
