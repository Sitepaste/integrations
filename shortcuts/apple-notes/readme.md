# Apple Notes

Publish notes from Apple Notes to Sitepaste using the Shortcuts app on macOS and iOS. Publish a single note or an entire folder.

Requires a Pro plan, as API tokens can only be created and used on the Pro plan.

## Prerequisites

- API token from Dashboard > Settings > Tokens (`sp_...`).
- macOS Monterey or later, or iOS 15 or later.

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

Inside the loop, add a single Get Contents of URL action. Set the URL to `https://sitepaste.com/api/v1/public/pages` and the method to `POST`. Add a header with key `Authorization` and value `Bearer ` followed by the `API Key` variable. Set the request body to JSON with these fields:

| Key | Type | Value |
|---|---|---|
| `title` | Text | Repeat Item with property set to `Name` |
| `content` | Text | Repeat Item with property set to `Body` |
| `contentType` | Text | `Content Type` variable |
| `section` | Text | Optional. Groups pages under a section: `/docs/{section}/{slug}` for docs and blog, `/{section}/{slug}` for standalone. |

To set a property, insert the variable into the value field, then tap the variable token and select the property from the list.

7. After the End Repeat marker, add a Get Contents of URL action. Set the URL to `https://sitepaste.com/api/v1/public/builds` and the method to `POST`. Add the same `Authorization` header as the loop action. No request body is needed.
8. Add a Show Alert action with the text "Published" followed by the `Note Count` variable followed by "notes to Sitepaste."

The slug for each page is auto-generated from the note title. Existing pages with the same slug are updated. Pages not in the folder are left untouched on Sitepaste.

## Publish a single note

Create a new shortcut named `Publish Note to Sitepaste`.

1. Add a Text action with your API token (`sp_...`). Name the output `API Key`.
2. Add a Choose from Menu action with three options: `Blog`, `Docs`, and `Standalone`. Under each branch, add a Text action containing `blog`, `docs`, or `standalone`. Name the output after the End Menu marker `Content Type`.
3. Add a Find Notes action. Set the sort to `Last Modified Date` and enable the limit with a value like `25`. Add a Choose from List action. Name the output `Note`.
4. Add a Get Contents of URL action. Set the URL to `https://sitepaste.com/api/v1/public/pages` and the method to `POST`. Add a header with key `Authorization` and value `Bearer ` followed by the `API Key` variable. Set the request body to JSON with these fields:

| Key | Type | Value |
|---|---|---|
| `title` | Text | `Note` variable with property set to `Name` |
| `content` | Text | `Note` variable with property set to `Body` |
| `contentType` | Text | `Content Type` variable |
| `section` | Text | Optional. Groups pages under a section: `/docs/{section}/{slug}` for docs and blog, `/{section}/{slug}` for standalone. |

5. Add a Get Dictionary Value action for the key `error` from the previous result. Add an If action with the condition `has any value`. Under the If branch, add a Show Alert action with "Error:" followed by the result. Under the Otherwise branch, add a Get Contents of URL action for `https://sitepaste.com/api/v1/public/builds` with the method `POST` and the same `Authorization` header, then a Show Alert with "Published to Sitepaste."

The slug is auto-generated from the title. Publishing the same note again updates the existing page.

## How it works

Each note is sent as a flat JSON object to `POST /api/v1/public/pages`. No arrays or nested structures are needed, which avoids known issues with the Shortcuts JSON body builder and complex payloads. A separate call to `POST /api/v1/public/builds` triggers the site build after all pages are created.

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

To publish as a draft, add a `draft` field to the JSON body:

| Key | Type | Value |
|---|---|---|
| `draft` | Boolean | `true` |

## Multiple sites

If your workspace has multiple sites, add a Text action right after the API key containing your target site ID. Name it `Site ID`. Then add a `siteId` field to the JSON body:

| Key | Type | Value |
|---|---|---|
| `siteId` | Text | `Site ID` variable |

Add the same `siteId` field to the build trigger request body so the correct site is built.

Site IDs are listed in Dashboard > Settings > Sites.

## Limitations

- Rich text formatting is stripped to plain text. Write in Markdown for best results.
- Images and file attachments embedded in notes cannot be extracted by Shortcuts. Upload media separately via the dashboard or the `POST /api/v1/public/media` endpoint.
- Checklists in Apple Notes are converted to plain text lines without checkbox syntax.
