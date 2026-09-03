import { requestUrl } from 'obsidian';

const API_BASE = 'https://sitepaste.com/api/v1/public';

// The site is part of the URI. 'default' names the workspace's default site,
// so leaving the setting blank still publishes somewhere sensible.
//
// Writing many pages goes to the collection's /batch sub-resource: a POST to
// the collection itself creates one page and refuses the envelope. Publishing
// is a second request to /deployments, so a refused deploy is its own status
// code rather than a field buried in the write's 200.
function pagesBatchUrl(siteId?: string): string {
  return `${API_BASE}/sites/${siteId || 'default'}/pages/batch`;
}

function deploymentsUrl(siteId?: string): string {
  return `${API_BASE}/sites/${siteId || 'default'}/deployments`;
}
const REQUEST_TIMEOUT_MS = 120_000;

export interface PagePayload {
  slug: string;
  title: string;
  content: string;
  contentType: string;
  section?: string;
  description?: string;
  apiEndpoint?: string;
  draft?: boolean;
  tags?: string[];
  publishedAt?: string;
  // Homepage only: whether recent posts and section listings show below the
  // content. A real boolean on the wire, unlike the tri-state theme overrides.
  showListings?: boolean;
  // Optional passthrough fields (author, password, OG image, language, and
  // per-page theme overrides), keyed by API field name — see extractOverrides
  // in utils.ts. Boolean overrides are the API's tri-state strings.
  authorId?: string;
  password?: string;
  ogImageUrl?: string;
  language?: string;
  theme?: string;
  primaryColor?: string;
  fontSize?: string;
  codeThemeLight?: string;
  codeThemeDark?: string;
  showToc?: string;
  showSocialShare?: string;
  showComments?: string;
  showNextPrev?: string;
  showNewsletterCta?: string;
  showTags?: string;
  showDates?: string;
  showAuthor?: string;
  showReadingTime?: string;
  showBreadcrumbs?: string;
  showCopyMarkdown?: string;
  showGalleryDownload?: string;
  fullWidthGallery?: string;
  masonryGallery?: string;
}

export interface PublishRequest {
  pages: PagePayload[];
}

export interface PageResult {
  id: string;
  slug: string;
  title: string;
  contentType: string;
  section?: string;
  status: 'created' | 'updated';
}

export interface PublishResponse {
  pages?: PageResult[];
  deleted?: string[];
}

// The deploy's own 202 body. A refusal is an ApiError instead, carrying the
// same {error, code, scope} envelope every other refusal on this API uses.
export interface DeployResponse {
  status?: string;
  deployUrl?: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: Record<string, unknown>,
  ) {
    const msg = (body['error'] as string) || `API returned ${status}`;
    super(msg);
    this.name = 'ApiError';
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise<never>((_, reject) => {
      timer = setTimeout(
        () =>
          reject(
            new Error('Request timed out. Your pages may have been saved — check the dashboard.'),
          ),
        ms,
      );
    }),
  ]);
}

export async function publishPages(
  apiKey: string,
  request: PublishRequest,
  siteId?: string,
): Promise<PublishResponse> {
  const response = await withTimeout(
    requestUrl({
      url: pagesBatchUrl(siteId),
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'User-Agent': 'Sitepaste-Obsidian',
      },
      body: JSON.stringify(request),
      throw: false,
    }),
    REQUEST_TIMEOUT_MS,
  );

  if (response.status >= 400) {
    let body: Record<string, unknown> = {};
    try {
      body = response.json;
    } catch {
      // noop
    }
    throw new ApiError(response.status, body);
  }

  try {
    return response.json as PublishResponse;
  } catch {
    throw new Error(
      'Publish may have succeeded but the response could not be parsed. Check the dashboard.',
    );
  }
}

// triggerDeploy publishes what publishPages just wrote.
//
// It is called only once the writes have landed, so a publish that failed is
// never followed by a build of the old content. A refusal throws an ApiError
// like any other, which is what lets the caller tell "the pages are saved but
// the site is still on its previous build" from "the pages were not saved".
export async function triggerDeploy(apiKey: string, siteId?: string): Promise<DeployResponse> {
  const response = await withTimeout(
    requestUrl({
      url: deploymentsUrl(siteId),
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'User-Agent': 'Sitepaste-Obsidian',
      },
      throw: false,
    }),
    REQUEST_TIMEOUT_MS,
  );

  if (response.status >= 400) {
    let body: Record<string, unknown> = {};
    try {
      body = response.json;
    } catch {
      // noop
    }
    throw new ApiError(response.status, body);
  }

  try {
    return response.json as DeployResponse;
  } catch {
    // The deploy is queued either way; only the URL to report is lost.
    return {};
  }
}
