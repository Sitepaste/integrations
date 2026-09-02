# Deploy to Sitepaste

A GitHub Action that syncs markdown files to [Sitepaste](https://sitepaste.com) and triggers a build.

Requires a Pro plan, as API tokens can only be created and used on the Pro plan.

The token needs the `content` and `deploy` scopes. `content` writes the pages and `deploy` publishes them. Scopes are chosen when the token is created in the dashboard under Account > Tokens, and cannot be changed afterwards. The deploy travels in the same `POST /sites/{siteId}/pages` request that writes the pages, but it is the same deploy `POST /sites/{siteId}/deployments` queues, and it requires that route's scope. A token holding `content` alone still syncs every page, and the deploy then comes back refused, which `fail-on-build-error` turns into a failed run.

## Quick start

```yaml
- uses: sitepaste/integrations/actions/deploy@v1
  with:
    api-token: ${{ secrets.SITEPASTE_TOKEN }}
    content-dir: docs
```

## Inputs

| Input          | Required | Default   | Description                                                   |
| -------------- | -------- | --------- | ------------------------------------------------------------- |
| `api-token`    | Yes      |           | Sitepaste API token (`sp_...`) with the `content` and `deploy` scopes. Store as a repository secret. |
| `content-dir`  | No       | `content` | Path to the directory containing markdown files.              |
| `content-type` | No       | `docs`    | Content type for all pages: `docs`, `blog`, or `standalone`.  |
| `site-id`      | No       |           | Target site ID, either the short ID shown in the dashboard or the full UUID. Omit to use the default site. |
| `dry-run`      | No       | `false`   | Validate and preview without syncing or building.             |
| `prune`        | No       | `false`   | Delete pages of this content type that are not in the content directory. See [Pruning](#pruning). |
| `fail-on-build-error` | No | `true`  | Fail the run when the pages were saved but the deploy was refused. See [Deploys](#deploys). |

## Sections

Subdirectories within the content directory become sections. For `docs` and `blog`, a section adds a path segment between the content type and the slug.

```
getting-started.md              (/docs/getting-started)
integrations/
  github.md                     (/docs/integrations/github)
  gitlab.md                     (/docs/integrations/gitlab)
guides/
  deployment.md                 (/docs/guides/deployment)
```

For `standalone`, a section becomes a custom top-level path:

```
about.md                        (/about)
handbook/
  onboarding.md                 (/handbook/onboarding)
  benefits.md                   (/handbook/benefits)
```

Standalone sections get their own styled landing page (`/handbook/`) and appear in the site navigation. Names that collide with existing root paths (`docs`, `blog`, `tags`, `media`, and a few others) are rejected, as are section names that match an existing root-level page slug on the site. Only the first directory level is checked against reserved names — `api/media/` is fine, because only `api` claims a top-level path.

Standalone sections may nest one level: a second directory becomes a sub-section, reaching the same depth docs and blog get from their content-type prefix.

```
api/
  overview.md                   (/api/overview)
  builds/
    post-builds.md              (/api/builds/post-builds)
```

Both levels get a landing page, and the sub-section appears in the navigation as a collapsible group inside its parent.

Pages with the same slug in different sections are allowed. Directories beyond the supported depth (one level for `docs` and `blog`, two for `standalone`) are ignored for the section, with a warning. A `section` field in front matter overrides the directory derived section and may itself be a nested path (`api/builds`) for standalone pages.

Directory casing carries through as the section's display name: a directory named `API/` publishes at `/api/` and displays as "API" in the site navigation, the same way typed casing works in the dashboard. Captured casing only fills in a display name where none is set yet — a rename made in the dashboard survives every deploy.

## Front matter

Optional YAML front matter is parsed from each markdown file:

```markdown
---
title: Getting Started
slug: getting-started
section: integrations
description: A guide to getting started
tags: [guides, setup]
draft: false
publishedAt: 2026-02-17
api_endpoint: GET /sites/{siteId}/pages/{slug}
---

Your content here...
```

All fields are optional. `slug` is derived from the filename when absent (lowercased, special characters replaced with hyphens). `title` is derived from the slug when absent (hyphens to spaces, capitalized). `section` is derived from the parent subdirectory when absent. All other fields are omitted from the API payload when absent, preserving any values set in the dashboard.

`publishedAt` accepts both date-only (`2026-02-17`) and full RFC 3339 (`2026-02-17T00:00:00Z`) formats.

`api_endpoint` marks the page as an API reference: an HTTP method optionally followed by a path (max 200 chars). The method shows as a badge next to the page in the site navigation.

`contentType` sets the page's type per file (`docs`, `blog`, `standalone`, or `homepage`), exactly as the pages API takes it; files without one use the workflow's `content-type` input. A `homepage` file publishes at `/` (its slug is fixed to `index`, as in the dashboard), must live at the content root, and a run can carry only one. Note that `prune` only reconciles pages of the input content type, so pages set to a different type per file are never pruned.

`show_listings` is the homepage's own setting — whether recent posts and section listings show below the content — and takes `true` or `false`. It means nothing on any other page, so the action warns and drops it rather than writing a setting the page cannot use.

`author` credits the page to an author, as an author ID from `GET /api/v1/public/sites/{siteId}/authors` — not a name, since author names are not unique. An empty string removes the author. `og_image_url` sets the social preview image, and `language` sets the page's language tag (`en`, `pt-BR`).

Per-page theme overrides pass through in snake_case: `theme`, `primary_color`, `font_size`, `code_theme_light`, and `code_theme_dark` as strings (empty string resets to inherit from the site), and the boolean overrides (`show_toc`, `show_social_share`, `show_comments`, `show_next_prev`, `show_newsletter_cta`, `show_tags`, `show_dates`, `show_author`, `show_reading_time`, `show_breadcrumbs`, `show_copy_markdown`, `show_gallery_download`, `full_width_gallery`, `masonry_gallery`) as `true`, `false`, or `"inherit"`.

A page `password` is deliberately not supported: front matter is committed to the repository, so the password would be readable by anyone with repo access and preserved in git history. The action fails the run if it finds one — set page passwords in the dashboard or through the API instead.

Tag casing is kept as the display name, the same way section directory casing is: a tag written as `iOS` is stored as `ios` and displays as iOS on the site. Captured casing fills a display name only where none is set yet.

## Content types

| Type         | Use case                               |
| ------------ | -------------------------------------- |
| `docs`       | Documentation, guides, reference pages |
| `blog`       | Blog posts, articles                   |
| `standalone` | Landing pages, about pages, custom top-level sections (`/handbook/...`) |
| `homepage`   | The site's `/` page. Per file only, via front matter |

The `content-type` input sets the type for every file in the run; a file that carries its own `contentType` in front matter overrides it. `homepage` is available only that way, since a site has exactly one and the input applies to the whole directory.

## How it works

1. Walks the content directory recursively for `.md` files, skipping hidden entries.
2. Derives sections from subdirectory names (overridable via front matter).
3. Parses front matter and derives missing slugs and titles from filenames.
4. Validates content limits and checks for duplicate slugs within each section.
5. Sends a single `POST /api/v1/public/sites/{siteId}/pages` request with all pages and `build: true`.
6. Reports results via GitHub Actions annotations.

## Deploys

The pages and the deploy travel in one request, so a run either writes every page or writes none, and the deploy is queued once the writes have landed.

The deploy can still be refused once the pages are saved. A token without the `deploy` scope, the monthly deploy quota, the 30-second cooldown between deploys, and an hourly budget of 300 deploys shared by every token in the workspace each do so on their own. In practice the cooldown is the one a busy repository meets, since it caps a site at 120 deploys an hour on its own. When that happens the pages are saved but the site keeps serving the previous build, so the run fails by default with the API's reason. Set `fail-on-build-error: 'false'` to report it as a warning and pass instead, which suits a workflow that deploys on a schedule rather than on every push.

`page-count` is set either way; `deploy-url` only when a deploy was actually queued.

Pages are created or updated by slug. By default, existing pages not in the batch are left untouched (additive only); set `prune: 'true'` to delete them instead.

## Pruning

By default the action is additive: deleting or renaming a file in the repository leaves the old page live on the site. With `prune: 'true'`, the content directory becomes the single source of truth for its content type, and any page not matched by a local file (by section and slug) is deleted in the same request that syncs the batch. Upserts, deletions, and the build are applied together, so the site never serves a half-synced state.

Only pages matching `content-type` are ever considered. The homepage, other content types, and other sites are untouched. But note that within that content type, the repository wins: pages created in the dashboard or via the Obsidian plugin will be deleted if they have no matching file. Enable pruning only when the repository owns that content type.

Combined with `dry-run: 'true'`, the action prints the pages that would be deleted without changing anything.

## Limits

| Field             | Max            |
| ----------------- | -------------- |
| Content           | 100000 bytes   |
| Slug              | 100 characters |
| Title             | 200 bytes      |
| Description       | 500 bytes      |
| Pages per request | 5000           |

## Examples

See [examples/](examples/) for ready-to-copy workflow files.

- [deploy-docs.yml](examples/deploy-docs.yml) syncs a `docs/` directory on push to main.
- [deploy-blog.yml](examples/deploy-blog.yml) publishes blog posts from a `posts/` directory.
- [preview-on-pr.yml](examples/preview-on-pr.yml) dry-run validation on pull requests.
