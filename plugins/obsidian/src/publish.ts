import { App, TFile, TFolder } from 'obsidian';
import type { PagePayload, PublishResponse } from './api';
import {
  byteLen,
  slugify,
  titleize,
  validatePage,
  VALID_CONTENT_TYPES,
  type ValidationError,
} from './utils';
import type { SitepasteSettings } from './settings';
import { publishPages } from './api';

export interface FilePublishInfo {
  file: TFile;
  slug: string;
  title: string;
  content: string;
  contentType: string;
  section?: string;
  description?: string;
  draft?: boolean;
  tags?: string[];
  publishedAt?: string;
  isUpdate: boolean;
  errors: ValidationError[];
}

function isDateOnly(s: string): boolean {
  if (s.length !== 10 || s[4] !== '-' || s[7] !== '-') return false;
  for (let i = 0; i < 10; i++) {
    if (i === 4 || i === 7) continue;
    if (s[i] < '0' || s[i] > '9') return false;
  }
  return true;
}

export async function prepareFile(
  app: App,
  file: TFile,
  defaultContentType: string,
): Promise<FilePublishInfo> {
  const raw = await app.vault.read(file);
  const cache = app.metadataCache.getFileCache(file);
  const fm = cache?.frontmatter ?? {};

  const rawSlug = fm['sitepaste-slug'] || fm['slug'];
  const slug = rawSlug ? String(rawSlug).toLowerCase().trim() : slugify(file.basename);
  const title = fm['title'] || titleize(slug);

  const fmContentType = fm['contentType'];
  const contentType =
    fmContentType && VALID_CONTENT_TYPES.has(fmContentType) ? fmContentType : defaultContentType;

  // strip frontmatter from content
  let content = raw;
  if (cache?.frontmatterPosition) {
    const end = cache.frontmatterPosition.end;
    const lines = raw.split('\n');
    content = lines.slice(end.line + 1).join('\n');
  } else {
    const startsLf = raw.startsWith('---\n');
    const startsCrlf = !startsLf && raw.startsWith('---\r\n');
    if (startsLf || startsCrlf) {
      const searchFrom = startsLf ? 4 : 5;
      let closeIdx = raw.indexOf('\n---\n', searchFrom);
      if (closeIdx !== -1) {
        content = raw.slice(closeIdx + 5);
      } else {
        closeIdx = raw.indexOf('\n---\r\n', searchFrom);
        if (closeIdx !== -1) {
          content = raw.slice(closeIdx + 6);
        } else if (raw.endsWith('\n---')) {
          content = '';
        }
      }
    }
  }

  const description = typeof fm['description'] === 'string' ? fm['description'] : undefined;
  const draft = typeof fm['draft'] === 'boolean' ? fm['draft'] : undefined;

  // extract section from frontmatter Obsidian folder structure is not used for sections
  const rawSection = fm['section'];
  const section = rawSection ? slugify(String(rawSection)) || undefined : undefined;

  let tags: string[] | undefined;
  if (fm['tags']) {
    const rawTags: unknown[] = Array.isArray(fm['tags']) ? fm['tags'] : [fm['tags']];
    tags = rawTags.map((t) => String(t).toLowerCase().trim()).filter((t) => t.length > 0);
  }

  let publishedAt: string | undefined;
  const pa = fm['publishedAt'] || fm['date'];
  if (pa instanceof Date && !isNaN(pa.getTime())) {
    // need RFC 3339 without fractional seconds
    const iso = pa.toISOString();
    publishedAt = iso.slice(0, 19) + 'Z';
  } else if (typeof pa === 'string') {
    publishedAt = isDateOnly(pa) ? pa + 'T00:00:00Z' : pa;
  }

  const isUpdate = !!fm['sitepaste-slug'];

  const errors = validatePage({ slug, title, content, section, description, tags, publishedAt });
  if (fmContentType && !VALID_CONTENT_TYPES.has(fmContentType)) {
    errors.push({
      field: 'contentType',
      message: `"${fmContentType}" is not a valid content type`,
    });
  }

  return {
    file,
    slug,
    title,
    content,
    contentType,
    section,
    description,
    draft,
    tags,
    publishedAt,
    isUpdate,
    errors,
  };
}

export async function doPublish(
  settings: SitepasteSettings,
  infos: FilePublishInfo[],
  triggerBuild?: boolean,
): Promise<PublishResponse> {
  const pages: PagePayload[] = infos.map((info) => {
    const page: PagePayload = {
      slug: info.slug,
      title: info.title,
      content: info.content,
      contentType: info.contentType,
    };
    if (info.section) page.section = info.section;
    if (info.description !== undefined) page.description = info.description;
    if (info.draft !== undefined) page.draft = info.draft;
    if (info.tags) page.tags = info.tags;
    if (info.publishedAt) page.publishedAt = info.publishedAt;
    return page;
  });

  const request = {
    pages,
    build: triggerBuild ?? settings.triggerBuild,
    ...(settings.siteId ? { siteId: settings.siteId } : {}),
  };

  return publishPages(settings.apiKey, request);
}

export async function updateFrontmatter(app: App, file: TFile, slug: string): Promise<void> {
  await app.fileManager.processFrontMatter(file, (fm) => {
    fm['sitepaste-slug'] = slug;
    fm['sitepaste-published'] = new Date().toISOString();
  });
}

export function collectMarkdownFiles(folder: TFolder): TFile[] {
  const files: TFile[] = [];
  for (const child of folder.children) {
    if (child instanceof TFile && child.extension === 'md') {
      files.push(child);
    } else if (child instanceof TFolder) {
      files.push(...collectMarkdownFiles(child));
    }
  }
  return files.sort((a, b) => a.path.localeCompare(b.path));
}

const MAX_BATCH_BYTES = 80_000_000;
const MAX_BATCH_PAGES = 2000;

export function splitIntoBatches(infos: FilePublishInfo[]): FilePublishInfo[][] {
  const batches: FilePublishInfo[][] = [];
  let current: FilePublishInfo[] = [];
  let currentBytes = 0;

  for (const info of infos) {
    const pageBytes = byteLen(info.content);
    if (
      current.length > 0 &&
      (currentBytes + pageBytes > MAX_BATCH_BYTES || current.length >= MAX_BATCH_PAGES)
    ) {
      batches.push(current);
      current = [];
      currentBytes = 0;
    }
    current.push(info);
    currentBytes += pageBytes;
  }
  if (current.length > 0) {
    batches.push(current);
  }
  return batches;
}
