import { requestUrl } from 'obsidian';

const API_BASE = 'https://sitepaste.com/api/v1/public';

// The site is part of the URI. 'default' names the workspace's default site,
// so leaving the setting blank still publishes somewhere sensible.
function pagesUrl(siteId?: string): string {
  return `${API_BASE}/sites/${siteId || 'default'}/pages`;
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
  build: boolean;
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
  // {status, deployUrl} once the deploy is queued, and {error, code} when it
  // was refused — the same triple the top-level error envelope uses, so a
  // refused deploy is read the same way whether it came back nested in a 200
  // or as the whole response. `scope` joins them when the refusal is that the
  // token lacks 'deploy'.
  build?: {
    status?: string;
    deployUrl?: string;
    error?: string;
    code?: string;
    scope?: string;
  };
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
      url: pagesUrl(siteId),
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
