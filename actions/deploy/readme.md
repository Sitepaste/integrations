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

## Front matter

Optional YAML front matter is parsed from each markdown file:

```markdown
---
title: Getting Started
slug: getting-started
description: A guide to getting started
tags: [guides, setup]
draft: false
publishedAt: 2026-02-17
---

Your content here...
```

All fields are optional. `slug` is derived from the filename when absent (lowercased, special characters replaced with hyphens). `title` is derived from the slug when absent (hyphens to spaces, capitalized). All other fields are omitted from the API payload when absent, preserving any values set in the dashboard.

`publishedAt` accepts both date-only (`2026-02-17`) and full RFC 3339 (`2026-02-17T00:00:00Z`) formats.

## Content types

| Type         | Use case                               |
| ------------ | -------------------------------------- |
| `docs`       | Documentation, guides, reference pages |
| `blog`       | Blog posts, articles                   |
| `standalone` | Landing pages, about pages             |

Every file in the batch uses the same content type.

## How it works

1. Walks the content directory recursively for `.md` files, skipping hidden entries.
2. Parses front matter and derives missing slugs and titles from filenames.
3. Validates content limits and checks for duplicate slugs.
4. Sends a single `POST /api/v1/public/pages` request with all pages and `build: true`.
5. Reports results via GitHub Actions annotations.

Pages are created or updated by slug. Existing pages not in the batch are left untouched (additive only).

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
