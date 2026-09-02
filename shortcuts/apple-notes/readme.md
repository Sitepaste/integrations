# Apple Notes

Publish notes from Apple Notes to Sitepaste using the Shortcuts app on macOS and iOS. Publish a single note or an entire folder.

Requires a Pro plan, as API tokens can only be created and used on the Pro plan.

## Prerequisites

- API token from Account > Tokens in the dashboard (`sp_...`).
- macOS Monterey or later, or iOS 15 or later.

Both shortcuts need a token with the `content` and `deploy` scopes, because they publish and then deploy. A deploy requires the `deploy` scope whether it is asked for with `build: true` in the same request or with a separate call to `POST /sites/{siteId}/deployments`. Scopes are chosen when the token is created and cannot be changed afterwards.

## Publish a folder

Create a new shortcut named `Publish Folder to Sitepaste`. This publishes every note in a folder using one content type, the same way the GitHub Action publishes a directory of markdown files.

### Settings

These actions go at the top of the shortcut. Edit them once to match your configuration.

1. Add a Text action with your API token (`sp_...`). Name the output `API Key`.
2. Add a Text action with the exact name of your Apple Notes folder (for example `Blog Posts`). Name the output `Folder Name`.
3. Add a Text action with the content type: `blog`, `docs`, or `standalone`. Name the output `Content Type`.

### Actions

4. Add a Find Notes action. Add a filter where Folder is the `Folder Name` variable. Set the sort to `Name`.
5. Add a Count action. Name the output `Note Count`.
6. Add a Repeat with Each action over the notes from step 4.

Inside the loop, add a single Get Contents of URL action. Set the URL to `https://sitepaste.com/api/v1/public/sites/default/pages` and the method to `POST`. Add a header with key `Authorization` and value `Bearer ` followed by the `API Key` variable. Set the request body to JSON with one field:

| Key | Type | Value |
|---|---|---|
| `pages` | Array | A single Dictionary item, with the keys below |

Inside that Dictionary item:

| Key | Type | Value |
|---|---|---|
| `title` | Text | Repeat Item with property set to `Name` |
| `content` | Text | Repeat Item with property set to `Body` |
| `contentType` | Text | `Content Type` variable |
| `section` | Text | Optional. Groups pages under a section: `/docs/{section}/{slug}` for docs and blog, `/{section}/{slug}` for standalone. |

To set a property, insert the variable into the value field, then tap the variable token and select the property from the list.

The body the action sends should look like this, with one note's values filled in:

```json
{ "pages": [{ "title": "My note", "content": "...", "contentType": "blog" }] }
```

7. After the End Repeat marker, add a Get Contents of URL action. Set the URL to `https://sitepaste.com/api/v1/public/sites/default/deployments` and the method to `POST`. Add the same `Authorization` header as the loop action. No request body is needed.
8. Add a Show Alert action with the text "Published" followed by the `Note Count` variable followed by "notes to Sitepaste."

The build stays outside the loop deliberately. Sitepaste enforces a 30-second cooldown between deploys, and an hourly budget of 300 deploys shared by the whole workspace on top of it, so building once per note would fail on the second note and burn the budget on work the last build redoes anyway.

The slug for each page is auto-generated from the note title. Existing pages with the same slug are updated. Pages not in the folder are left untouched on Sitepaste.

## Publish a single note

Create a new shortcut named `Publish Note to Sitepaste`.

1. Add a Text action with your API token (`sp_...`). Name the output `API Key`.
2. Add a Choose from Menu action with three options: `Blog`, `Docs`, and `Standalone`. Under each branch, add a Text action containing `blog`, `docs`, or `standalone`. Name the output after the End Menu marker `Content Type`.
3. Add a Find Notes action. Set the sort to `Last Modified Date` and enable the limit with a value like `25`. Add a Choose from List action. Name the output `Note`.
4. Add a Get Contents of URL action. Set the URL to `https://sitepaste.com/api/v1/public/sites/default/pages` and the method to `POST`. Add a header with key `Authorization` and value `Bearer ` followed by the `API Key` variable. Set the request body to JSON with these fields:

| Key | Type | Value |
|---|---|---|
| `pages` | Array | A single Dictionary item, with the keys below |
| `build` | Boolean | `true`, so the note publishes and the site deploys in one request |

Inside the Dictionary item:

| Key | Type | Value |
|---|---|---|
| `title` | Text | `Note` variable with property set to `Name` |
| `content` | Text | `Note` variable with property set to `Body` |
| `contentType` | Text | `Content Type` variable |
| `section` | Text | Optional. Groups pages under a section: `/docs/{section}/{slug}` for docs and blog, `/{section}/{slug}` for standalone. |

The body the action sends should look like this:

```json
{ "pages": [{ "title": "My note", "content": "...", "contentType": "blog" }], "build": true }
```

5. Add a Get Dictionary Value action for the key `error` from the previous result. Add an If action with the condition `has any value`. Under the If branch, add a Show Alert action with "Error:" followed by the result. Under the Otherwise branch, add a Show Alert with "Published to Sitepaste."

The slug is auto-generated from the title. Publishing the same note again updates the existing page.

The note is saved before the deploy is queued, so a refused deploy does not lose the note: it comes back in the response's `build` field rather than in `error`, and the next run deploys it along with whatever else changed.

## How it works

Each note is sent to `POST /api/v1/public/sites/default/pages` as one entry in the request's `pages` array. The `pages` key is what makes the request a batch: the same route also takes a single page as a flat object with `title` and `content` at the top level, but that form creates a page and answers `409` if one already exists, where the batch updates it. Both shortcuts re-publish the same notes over time, so both use the array.

The single-note shortcut sets `build: true` and is done in one request. The folder shortcut posts each note on its own and then calls `POST /api/v1/public/sites/default/deployments` once, after the loop.

Pages are created or updated by slug. Existing pages not in the batch are left untouched.

## Content types

| Type | Use case |
|---|---|
| `blog` | Blog posts, articles |
| `docs` | Documentation, guides, reference pages |
| `standalone` | Landing pages, about pages |

> The `homepage` content type exists but should be published individually through the dashboard, since a site can only have one.

## Writing tips

Apple Notes stores rich text internally, but Shortcuts retrieves note content as plain text. Formatting like bold, italic, and headings is stripped during extraction. For best results, write using Markdown syntax directly in your notes.

```
## A heading

A paragraph with **bold** and _italic_ text.

- First item
- Second item

[Link text](https://example.com)
```

## Note body and title

The first line of an Apple Notes body may repeat the note title. If the title appears duplicated on your published page, add a Replace Text action before the Get Contents of URL action. Insert the note variable with the `Body` property, enable Regular Expression, set the find pattern to `^.*\n`, and leave the replacement empty. Use the Replace Text output as the `content` value instead of the note body directly.

In the folder shortcut, this Replace Text action goes inside the Repeat with Each loop before the Get Contents of URL action.

## Draft mode

To publish as a draft, add a `draft` field to the page Dictionary, alongside `title` and `content`:

| Key | Type | Value |
|---|---|---|
| `draft` | Boolean | `true` |

## Multiple sites

The site is named in the URL, not in the request body. Every URL above uses `sites/default`, which follows whichever site your workspace has set as its default; to publish somewhere else, put that site's ID where `default` sits:

```
https://sitepaste.com/api/v1/public/sites/YOUR_SITE_ID/pages
https://sitepaste.com/api/v1/public/sites/YOUR_SITE_ID/deployments
```

Change it in the folder shortcut's build trigger too, so the site you published to is the site that gets built.

A `siteId` field in the JSON body is refused with a `422`, rather than ignored — a request that believes it is writing to one site while the URL names another should not land quietly on the wrong one.

The active site's ID is shown in the dashboard under Account, and clicking it copies it; switch sites to read another one's. Either that short ID or the site's full UUID works in the URL.

## Limitations

- Rich text formatting is stripped to plain text. Write in Markdown for best results.
- Images and file attachments embedded in notes cannot be extracted by Shortcuts. Upload media separately via the dashboard, or via the `POST /api/v1/public/media` endpoint with a token that has the `media` scope.
- Checklists in Apple Notes are converted to plain text lines without checkbox syntax.
- The folder shortcut sends one request per note, and the API allows 600 requests a minute — keyed on your IP address and client, so other traffic from the same network shares the budget. A folder of several hundred notes can start getting `429` responses partway through; run it on smaller folders, or publish the folder from the [GitHub Action](../../actions/deploy) or the [Obsidian plugin](../../plugins/obsidian), which send every page in one batch.
