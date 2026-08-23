# Sitepaste Obsidian plugin

Publish markdown files directly from Obsidian. Publish a single file or an entire folder.

## Setup

1. Copy the plugin files (`main.js`, `manifest.json`, `styles.css`) to your vault's `.obsidian/plugins/sitepaste/` directory.
2. Enable the plugin in Settings > Community Plugins.
3. Go to Settings > Sitepaste and enter your API key (found in Dashboard > Tokens).

## Settings

| Setting | Description |
|---|---|
| API key | Your Sitepaste API key (`sp_...`). Required. |
| Site ID | Optional. Publishes to a specific site. Leave empty for your default site. |
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

All markdown files in the folder (recursively) are published in a single batch API call.

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
| `draft` | `true` or `false`. |
| `tags` | Array of tags (max 20, each max 30 chars). |
| `publishedAt` | ISO date or datetime. Also reads `date`. |

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
