# Sitepaste Obsidian plugin

Publish markdown files directly from Obsidian. Publish a single file or an entire folder.

## Setup

1. Copy the plugin files (`main.js`, `manifest.json`, `styles.css`) to your vault's `.obsidian/plugins/sitepaste/` directory.
2. Enable the plugin in Settings > Community Plugins.
3. Go to Settings > Sitepaste and enter your API key, created in the dashboard under Account > Tokens.

The token needs the `content` and `deploy` scopes. `content` publishes the notes and `deploy` puts them live. Scopes are chosen when a token is created and cannot be changed afterwards, so a token minted without them has to be replaced. The build travels in the same `POST /sites/{siteId}/pages` request that publishes the notes, but it is the same deploy `POST /sites/{siteId}/deployments` queues, and it requires that route's scope. With `content` alone the notes still publish and only the build is refused, which is the same outcome as turning **Trigger build** off.

## Settings

| Setting | Description |
|---|---|
| API key | Your Sitepaste API key (`sp_...`). Required. |
| Site ID | Optional. Publishes to a specific site, by the short ID shown in the dashboard or the full UUID. Leave empty for your default site. |
| Default content type | `docs`, `blog`, or `standalone`. Used when a file has no `contentType` in frontmatter. |
| Trigger build | Trigger a site build after publishing. Disable to save build quota. Enabled by default. |
| Dry run | When enabled, validates locally and show a summary without calling the API. |

## Usage

### Publish a single file

- Click the upload ribbon icon (publishes the active file)
- Use the command palette: `Sitepaste: Publish current file`
- Right-click a `.md` file > `Publish to Sitepaste`

### Publish a folder

- Right-click a folder > `Publish folder to Sitepaste`

All markdown files in the folder (recursively) are published together. Large folders are split into several batch requests, and only the last one triggers the build, so a folder publish costs one deploy however many files it carries.

## Frontmatter

Control publishing behavior with frontmatter fields:

```yaml
---
title: My Page Title
slug: custom-slug
contentType: blog
section: guides
description: A short description
draft: true
tags: [tag1, tag2]
publishedAt: 2025-01-15
---
```

| Field | Description |
|---|---|
| `title` | Page title. Defaults to title-cased filename. |
| `slug` | URL slug. Defaults to slugified filename. |
| `contentType` | `docs`, `blog`, `homepage`, or `standalone`. Overrides the default setting. `homepage` must be published individually (not as part of a folder batch) since a site can only have one. |
| `section` | Optional section. For docs and blog pages it creates URLs like `/docs/{section}/{slug}`; for standalone pages it becomes a custom top-level path like `/{section}/{slug}` (some names like `docs`, `blog` are reserved). The value is normalized to slug format. Vault folder structure is not used for sections so this must be set explicitly. |
| `description` | Short description (max 500 bytes). |
| `api_endpoint` | Marks the page as an API reference: an HTTP method optionally followed by a path, like `GET /sites/{siteId}/pages/{slug}` (max 200 chars). The method shows as a badge next to the page in the site navigation. |
| `draft` | `true` or `false`. |
| `tags` | Array of tags (max 20, each max 30 chars). |
| `publishedAt` | ISO date or datetime. Also reads `date`. |
| `show_listings` | Homepage only: whether recent posts and section listings show below the content. `true` or `false`. Ignored on any other content type. |
| `author` | Author to credit the page to, as an author ID from `GET /api/v1/public/sites/{siteId}/authors` — not a name, since author names are not unique. An empty string removes the author. |
| `password` | Password-protects the page (min 8 chars, Pro plan). An empty string removes the protection. Your vault is private, so this is as safe as typing it in the dashboard — but avoid it in a vault synced to a shared repository. |
| `og_image_url` | Social preview image URL. |
| `language` | Language tag for the page, like `en` or `pt-BR`. |
| `theme`, `primary_color`, `font_size`, `code_theme_light`, `code_theme_dark` | Per-page theme overrides. An empty string resets a field to inherit from the site. |
| `show_toc`, `show_social_share`, `show_comments`, `show_next_prev`, `show_newsletter_cta`, `show_tags`, `show_dates`, `show_author`, `show_reading_time`, `show_breadcrumbs`, `show_copy_markdown`, `show_gallery_download`, `full_width_gallery`, `masonry_gallery` | Boolean theme overrides: `true`, `false`, or `"inherit"`. |

After publishing, the plugin writes two tracking fields:

- `sitepaste-slug` — the slug used. Presence of this field means re-publishing will update the page.
- `sitepaste-published` — timestamp of the last publish.

## Dry run

Enable dry run in settings to validate files without publishing. A summary modal shows each file's slug, content type, action (Create/Update), and any validation errors.

## Building from source

```sh
npm install
npm run build
```

This produces `main.js` in the plugin root. Copy `main.js`, `manifest.json`, and `styles.css` to your vault's plugin directory.
