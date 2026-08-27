import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import NoReturn

API = "https://sitepaste.com/api/v1/public/pages"
TYPES = {"docs", "blog", "standalone"}
MAX_SLUG_LENGTH = 100
MAX_TAGS_COUNT = 20
API_ENDPOINT_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
MAX_TAG_LENGTH = 30

# Optional front matter fields passed through to the API (front matter key ->
# API payload field). `author` is an author ID from GET /api/v1/public/authors;
# pages reference authors by ID because author names are not unique. An empty
# string clears the field on an existing page.
PASSTHROUGH_STRING_FIELDS = {
    "author": "authorId",
    "og_image_url": "ogImageUrl",
    "language": "language",
    "theme": "theme",
    "primary_color": "primaryColor",
    "font_size": "fontSize",
    "code_theme_light": "codeThemeLight",
    "code_theme_dark": "codeThemeDark",
}

# Per-page boolean theme overrides. Tri-state on the API ("true", "false",
# "inherit") so an explicit off stays distinct from inherit-from-site; front
# matter accepts YAML booleans or the string "inherit".
TRISTATE_FIELDS = {
    "show_toc": "showToc",
    "show_social_share": "showSocialShare",
    "show_comments": "showComments",
    "show_next_prev": "showNextPrev",
    "show_newsletter_cta": "showNewsletterCta",
    "show_tags": "showTags",
    "show_dates": "showDates",
    "show_author": "showAuthor",
    "show_reading_time": "showReadingTime",
    "show_breadcrumbs": "showBreadcrumbs",
    "show_copy_markdown": "showCopyMarkdown",
    "show_gallery_download": "showGalleryDownload",
    "full_width_gallery": "fullWidthGallery",
    "masonry_gallery": "masonryGallery",
}

VALID_FONT_SIZES = {"compact", "comfortable", "large"}
# Mirrors the API's language validation: a 2-3 letter primary subtag plus
# optional 1-8 char alphanumeric subtags (singletons and private use
# included), at most 35 characters.
LANGUAGE_RE = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*")
MAX_LANGUAGE_LENGTH = 35


def get_input(name):
    key = "INPUT_" + name.upper().replace("-", "_")
    return os.environ.get(key, "").strip()


def set_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with Path(path).open("a") as f:
            f.write(f"{name}={value}\n")


def error(msg, file=None):
    if file:
        print(f"::error file={file}::{msg}")
    else:
        print(f"::error::{msg}")


def warn(msg, file=None):
    if file:
        print(f"::warning file={file}::{msg}")
    else:
        print(f"::warning::{msg}")


def die(msg, file=None) -> NoReturn:
    error(msg, file)
    sys.exit(1)


def strip_quotes(s):
    if len(s) >= 2 and s[0] in ('"', "'") and s[-1] == s[0]:
        return s[1:-1]
    return s


def is_date_only(s):
    return len(s) == 10 and s[4] == s[7] == "-" and (s[:4] + s[5:7] + s[8:]).isdigit()


def parse_front_matter(raw):
    lines = raw.split("\n")
    if lines[0].rstrip("\r") != "---":
        return {}, raw
    close = -1
    for i in range(1, min(len(lines), 31)):
        if lines[i].rstrip("\r") == "---":
            close = i
            break
    if close == -1:
        return {}, raw
    attrs = {}
    for i in range(1, close):
        line = lines[i].rstrip("\r")
        sep = line.find(": ")
        if sep == -1:
            continue
        key = line[:sep].strip()
        val = line[sep + 2 :].strip()
        if val == "true":
            val = True
        elif val == "false":
            val = False
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            val = [strip_quotes(s.strip()) for s in inner.split(",")] if inner else []
        else:
            val = strip_quotes(val)
        attrs[key] = val
    body = "\n".join(lines[close + 1 :])
    return attrs, body


def _normalize_slug(name, keep_case=False):
    if not keep_case:
        name = name.lower()
    result = []
    last_was_hyphen = True
    for ch in name:
        if ch == "'":
            continue
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9"):
            result.append(ch)
            last_was_hyphen = False
        elif not last_was_hyphen:
            result.append("-")
            last_was_hyphen = True
    s = "".join(result)
    if s.endswith("-"):
        s = s[:-1]
    if len(s) > MAX_SLUG_LENGTH:
        s = s[:MAX_SLUG_LENGTH]
        if s.endswith("-"):
            s = s[:-1]
    return s


def slugify(rel_path):
    return _normalize_slug(Path(rel_path).stem)


def normalize_section(value, keep_case=False):
    """Normalize a section path per slash-separated segment, so a nested
    standalone section ("api/builds") keeps its separator instead of having
    it collapsed into a hyphen. Empty segments (leading, trailing, or doubled
    slashes) drop out. Whether nesting is allowed at all is the caller's
    check — docs and blog sections stay single-segment.

    With keep_case, casing survives ("API/Builds"): the server lowercases it
    into the stored slug and captures the typed casing as the section's
    display title, the same way the dashboard picker does — so a directory
    named API/ labels the section "API", not the titleized "Api"."""
    segments = (_normalize_slug(p, keep_case) for p in str(value).split("/"))
    return "/".join(s for s in segments if s)


def titleize(slug):
    return " ".join(w[0].upper() + w[1:] for w in slug.split("-") if w)


def is_valid_slug(slug):
    if not slug:
        return False
    for i, ch in enumerate(slug):
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            continue
        if ch == "-" and 0 < i < len(slug) - 1:
            continue
        return False
    return True


def is_valid_tag(tag):
    for ch in tag:
        if ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == " " or ch == "-":
            continue
        return False
    return True


def is_valid_published_at(s):
    try:
        datetime.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


def find_relative_images(text):
    refs = []
    i = 0
    while i < len(text):
        start = text.find("![", i)
        if start == -1:
            break
        close_bracket = text.find("]", start + 2)
        if close_bracket == -1:
            break
        if close_bracket + 1 >= len(text) or text[close_bracket + 1] != "(":
            i = close_bracket + 1
            continue
        close_paren = text.find(")", close_bracket + 2)
        if close_paren == -1:
            break
        url = text[close_bracket + 2 : close_paren]
        if not url.startswith("http://") and not url.startswith("https://"):
            refs.append(url)
        i = close_paren + 1
    return refs


def fetch_remote_pages(token, content_type, site_id):
    url = f"{API}?contentType={content_type}"
    if site_id:
        url += f"&siteId={site_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "Sitepaste-Deploy",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read())
        except Exception:
            data = {}
        detail = data.get("error", "unknown error")
        die(f"could not list remote pages for prune, api returned {e.code}: {detail}")
    except urllib.error.URLError as e:
        die(f"could not list remote pages for prune: {e.reason}")
    except TimeoutError:
        die("could not list remote pages for prune: request timed out after 120 seconds")
    return data.get("pages", [])


def page_url(content_type, section, slug):
    if content_type == "homepage":
        return "/"
    if content_type == "standalone":
        return f"/{section}/{slug}" if section else f"/{slug}"
    if section:
        return f"/{content_type}/{section}/{slug}"
    return f"/{content_type}/{slug}"


def walk_md(directory):
    base = Path(directory)
    if not base.is_dir():
        raise OSError(f"No such directory: '{directory}'")
    results = []
    for full in sorted(base.rglob("*.md")):
        if any(p.startswith(".") for p in full.relative_to(base).parts):
            continue
        rel = str(full.relative_to(base))
        results.append((full, rel))
    return results


def main():
    token = get_input("api-token")
    directory = get_input("content-dir") or "content"
    content_type = get_input("content-type") or "docs"
    site_id = get_input("site-id")
    dry_run = get_input("dry-run") == "true"
    prune = get_input("prune") == "true"

    if token:
        print(f"::add-mask::{token}")

    if not token:
        die("api-token is required, set it as a secret in your repository settings")
    if content_type not in TYPES:
        die(f'invalid content-type "{content_type}", must be one of docs, blog, or standalone')

    try:
        files = walk_md(directory)
    except OSError as e:
        die(f'could not read directory "{directory}": {e}')

    if not files:
        warn(f"No markdown files found in {directory}.")
        return

    entries = []
    slugs = {}
    valid = True

    for full, rel in files:
        raw = full.read_text(encoding="utf-8")

        attrs, body = parse_front_matter(raw)

        # Per-file contentType, exactly as the pages API and the Obsidian
        # plugin take it; the content-type input is only the default for
        # files that don't set one.
        file_content_type = content_type
        fm_content_type = str(attrs.get("contentType") or "").strip()
        if fm_content_type:
            if fm_content_type in TYPES or fm_content_type == "homepage":
                file_content_type = fm_content_type
            else:
                error(
                    f'contentType "{fm_content_type}" must be one of'
                    " docs, blog, standalone, or homepage",
                    rel,
                )
                valid = False

        slug = attrs.get("slug") or slugify(rel)
        if file_content_type == "homepage":
            slug = "index"  # the homepage's fixed slug, as in the dashboard
        title = attrs.get("title") or titleize(slug)

        # extract section from directory structure. Standalone sections may
        # nest one level (api/builds/x.md -> section "api/builds"), matching
        # the depth docs/blog reach via their content-type prefix — which is
        # also why docs/blog directories stay single-level.
        dirs = Path(rel).parts[:-1]
        max_section_dirs = 2 if file_content_type == "standalone" else 1
        section = None
        if len(dirs) > max_section_dirs:
            used = "/".join(dirs[:max_section_dirs])
            depth = "one level" if max_section_dirs == 1 else "two levels"
            warn(
                f"{rel} is nested more than {depth} deep; "
                f"using '{used}' as section, ignoring deeper nesting",
                rel,
            )
        # Casing survives into the payload ("API/Builds"): the server stores
        # the lowercase slug and captures the typed casing as the section's
        # display title (where none is set yet). Local dedup and prune
        # matching key on the lowercase slug, which is what the API returns.
        if dirs:
            section = normalize_section("/".join(dirs[:max_section_dirs]), keep_case=True)
        if "section" in attrs:
            section = normalize_section(str(attrs["section"]), keep_case=True)
        if section == "":
            section = None
        if file_content_type == "homepage" and section is not None:
            error("a homepage cannot have a section; move the file to the content root", rel)
            valid = False
            section = None
        section_key = section.lower() if section else None
        if section is not None and section.count("/") + 1 > max_section_dirs:
            # Only reachable via front matter — the directory path is capped
            # above. Caught locally so the run fails with the file named,
            # instead of a server-side validation error.
            what = (
                f"{file_content_type} sections cannot nest"
                if max_section_dirs == 1
                else "standalone sections nest at most one level"
            )
            error(f'section "{section}" is invalid: {what}', rel)
            valid = False

        body_size = len(body.encode("utf-8"))
        title_size = len(title.encode("utf-8"))

        if body_size > 100_000:
            error(f"content exceeds 100000 byte limit ({body_size} bytes)", rel)
            valid = False
        if len(slug) > MAX_SLUG_LENGTH:
            error(f"slug exceeds {MAX_SLUG_LENGTH} character limit ({len(slug)} chars)", rel)
            valid = False
        elif not is_valid_slug(slug):
            error(
                f'slug "{slug}" contains invalid characters'
                " (only lowercase letters, numbers, and hyphens allowed,"
                " must start and end with a letter or number)",
                rel,
            )
            valid = False
        if title_size > 200:
            error(f"title exceeds 200 byte limit ({title_size} bytes)", rel)
            valid = False
        if attrs.get("description"):
            desc_size = len(attrs["description"].encode("utf-8"))
            if desc_size > 500:
                error(f"description exceeds 500 byte limit ({desc_size} bytes)", rel)
                valid = False
        api_endpoint = str(attrs.get("api_endpoint") or "").strip()
        if api_endpoint:
            method = api_endpoint.split(" ", 1)[0].upper()
            if method not in API_ENDPOINT_METHODS:
                error(
                    f'api_endpoint "{api_endpoint}" must start with an HTTP method '
                    f"({', '.join(sorted(API_ENDPOINT_METHODS))})",
                    rel,
                )
                valid = False
            elif len(api_endpoint) > 200:
                error(f"api_endpoint exceeds 200 character limit ({len(api_endpoint)} chars)", rel)
                valid = False

        dedup_key = f"{file_content_type}:{section_key or ''}:{slug}"
        if dedup_key in slugs:
            error(
                f'duplicate slug "{slug}" (section "{section or ""}"),'
                f" also produced by {slugs[dedup_key]}",
                rel,
            )
            valid = False
        else:
            slugs[dedup_key] = rel

        for ref in find_relative_images(body):
            warn(
                f'Contains relative image reference "{ref}". '
                "Upload media separately via the dashboard or POST /api/v1/public/media.",
                rel,
            )

        page = {"slug": slug, "title": title, "content": body, "contentType": file_content_type}
        if section:
            page["section"] = section
        if "description" in attrs:
            page["description"] = attrs["description"]
        if api_endpoint:
            page["apiEndpoint"] = api_endpoint
        if "draft" in attrs:
            page["draft"] = attrs["draft"]
        if attrs.get("tags"):
            raw_tags = attrs["tags"]
            if not isinstance(raw_tags, list):
                raw_tags = [raw_tags]
            # Typed casing survives ("iOS"): the server stores the lowercase
            # slug and captures the casing as the tag's display title (where
            # none is set yet), matching the dashboard. Validation runs on
            # the lowercase form the server will store.
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]
            if len(tags) > MAX_TAGS_COUNT:
                error(f"too many tags ({len(tags)}, max {MAX_TAGS_COUNT})", rel)
                valid = False
            for tag in tags:
                if len(tag) > MAX_TAG_LENGTH:
                    error(f'tag "{tag}" exceeds {MAX_TAG_LENGTH} character limit', rel)
                    valid = False
                elif not is_valid_tag(tag.lower()):
                    error(f'tag "{tag}" contains invalid characters', rel)
                    valid = False
            if tags:
                page["tags"] = tags
        pa = attrs.get("publishedAt") or attrs.get("date")
        if pa:
            published_at = pa + "T00:00:00Z" if is_date_only(pa) else pa
            if not is_valid_published_at(published_at):
                error(f'publishedAt "{pa}" is not a valid date', rel)
                valid = False
            else:
                page["publishedAt"] = published_at

        # A page password is deliberately NOT supported here: front matter is
        # committed to the repository, so the password would be readable by
        # anyone with repo access and kept forever in git history. Ignoring
        # the field silently would be worse — the page would publish
        # unprotected while the file says otherwise — so the run fails.
        if "password" in attrs:
            error(
                "password front matter is not supported by the GitHub Action;"
                " a password committed to a repository is not a secret."
                " Set page passwords in the dashboard or via the API instead.",
                rel,
            )
            valid = False

        for key, api_field in PASSTHROUGH_STRING_FIELDS.items():
            if key not in attrs:
                continue
            value = str(attrs[key]).strip()
            if key == "author" and value and (" " in value or len(value) > 40):
                error(
                    f'author "{value}" must be an author ID from GET /authors, not a name'
                    " (author names are not unique)",
                    rel,
                )
                valid = False
            elif (
                key == "og_image_url"
                and value
                and not value.startswith(("http://", "https://", "/media"))
            ):
                error(f'og_image_url "{value}" must be an http(s) URL or a /media path', rel)
                valid = False
            elif (
                key == "language"
                and value
                and (len(value) > MAX_LANGUAGE_LENGTH or not LANGUAGE_RE.fullmatch(value))
            ):
                error(f'language "{value}" must be a language tag like "en" or "pt-BR"', rel)
                valid = False
            elif key == "font_size" and value and value not in VALID_FONT_SIZES:
                error(f'font_size "{value}" must be one of: compact, comfortable, large', rel)
                valid = False
            else:
                page[api_field] = value

        for key, api_field in TRISTATE_FIELDS.items():
            if key not in attrs:
                continue
            value = attrs[key]
            if value is True or value is False:
                page[api_field] = "true" if value else "false"
            elif str(value).strip() in ("true", "false", "inherit"):
                page[api_field] = str(value).strip()
            else:
                error(f'{key} "{value}" must be true, false, or "inherit"', rel)
                valid = False

        entries.append((rel, page))

    if not valid:
        sys.exit(1)

    if len(entries) > 5000:
        die(f"{len(entries)} pages exceeds the 5000 page limit")

    print(f"Syncing {len(entries)} page(s) as {content_type}:")
    for rel, page in entries:
        # Standalone pages publish at the root; a section becomes a
        # custom top-level path: /{section}/{slug}
        section_slug = (page.get("section") or "").lower() or None
        print(f"  {rel} to {page_url(page['contentType'], section_slug, page['slug'])}")

    delete_slugs = []
    if prune:
        for remote in fetch_remote_pages(token, content_type, site_id):
            if remote.get("contentType") != content_type:
                continue
            key = f"{content_type}:{remote.get('section') or ''}:{remote['slug']}"
            if key in slugs:
                continue
            entry = {"slug": remote["slug"], "contentType": content_type}
            if remote.get("section"):
                entry["section"] = remote["section"]
            delete_slugs.append(entry)
        if len(delete_slugs) > 5000:
            die(f"{len(delete_slugs)} pages to prune exceeds the 5000 page limit")
        if delete_slugs:
            verb = "Would prune" if dry_run else "Pruning"
            print(f"{verb} {len(delete_slugs)} page(s) not in {directory}:")
            for entry in delete_slugs:
                print(f"  {page_url(content_type, entry.get('section'), entry['slug'])}")

    if dry_run:
        print("Dry run complete. No changes were made.")
        return

    pages = [page for _, page in entries]
    payload = {"pages": pages, "build": True}
    if delete_slugs:
        payload["deleteSlugs"] = delete_slugs
    if site_id:
        payload["siteId"] = site_id

    body_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API,
        data=body_bytes,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Sitepaste-Deploy",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read())
        except Exception:
            data = {}
        if e.code == 400 and "pages" in data:
            for idx_str, field_errors in data["pages"].items():
                idx = int(idx_str)
                file = entries[idx][0] if idx < len(entries) else f"page {idx_str}"
                for field, msg in field_errors.items():
                    error(f"validation failed for {field}: {msg}", file)
        else:
            error(f"api returned {e.code}: {data.get('error', 'unknown error')}")
        sys.exit(1)
    except urllib.error.URLError as e:
        die(f"request failed: {e.reason}")
    except TimeoutError:
        die("request timed out after 120 seconds")

    set_output("page-count", len(pages))
    print(f"Synced {len(pages)} page(s) successfully.")
    if delete_slugs:
        print(f"Pruned {len(data.get('deleted', []))} page(s).")

    build = data.get("build", {})
    if build.get("error"):
        warn(f"Build was not triggered: {build.get('message') or build['error']}")
    elif build.get("deployUrl"):
        set_output("deploy-url", build["deployUrl"])
        print(f"Deployed to {build['deployUrl']}")


if __name__ == "__main__":
    main()
