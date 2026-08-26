# Deploy to Sitepaste

A GitHub Action that syncs markdown files to [Sitepaste](https://sitepaste.com) and triggers a build.

Requires a Pro plan, as API tokens can only be created and used on the Pro plan.

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
| `api-token`    | Yes      |           | Sitepaste API token (`sp_...`). Store as a repository secret. |
| `content-dir`  | No       | `content` | Path to the directory containing markdown files.              |
| `content-type` | No       | `docs`    | Content type for all pages: `docs`, `blog`, or `standalone`.  |
| `site-id`      | No       |           | Target site UUID. Omit to use the default site.               |
| `dry-run`      | No       | `false`   | Validate and preview without syncing or building.             |
| `prune`        | No       | `false`   | Delete pages of this content type that are not in the content directory. See [Pruning](#pruning). |

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
api_endpoint: GET /pages/{slug}
---

Your content here...
```

All fields are optional. `slug` is derived from the filename when absent (lowercased, special characters replaced with hyphens). `title` is derived from the slug when absent (hyphens to spaces, capitalized). `section` is derived from the parent subdirectory when absent. All other fields are omitted from the API payload when absent, preserving any values set in the dashboard.

`publishedAt` accepts both date-only (`2026-02-17`) and full RFC 3339 (`2026-02-17T00:00:00Z`) formats.

`api_endpoint` marks the page as an API reference: an HTTP method optionally followed by a path (max 200 chars). The method shows as a badge next to the page in the site navigation.

Tag casing is kept as the display name, the same way section directory casing is: a tag written as `iOS` is stored as `ios` and displays as iOS on the site. Captured casing fills a display name only where none is set yet.

## Content types

| Type         | Use case                               |
| ------------ | -------------------------------------- |
| `docs`       | Documentation, guides, reference pages |
| `blog`       | Blog posts, articles                   |
| `standalone` | Landing pages, about pages, custom top-level sections (`/handbook/...`) |

Every file in the batch uses the same content type.

> The `homepage` content type exists but is not supported by this action. A site can only have one homepage, so it must be published individually through the dashboard or the Obsidian plugin's single-file publish.

## How it works

1. Walks the content directory recursively for `.md` files, skipping hidden entries.
2. Derives sections from subdirectory names (overridable via front matter).
3. Parses front matter and derives missing slugs and titles from filenames.
4. Validates content limits and checks for duplicate slugs within each section.
5. Sends a single `POST /api/v1/public/pages` request with all pages and `build: true`.
6. Reports results via GitHub Actions annotations.

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
