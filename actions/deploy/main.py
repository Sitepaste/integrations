import json
import os
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
MAX_TAG_LENGTH = 30


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


def _normalize_slug(name):
    name = name.lower()
    result = []
    last_was_hyphen = True
    for ch in name:
        if ch == "'":
            continue
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
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
        slug = attrs.get("slug") or slugify(rel)
        title = attrs.get("title") or titleize(slug)

        # extract section from directory structure
        parts = Path(rel).parts
        section = None
        if len(parts) > 2:
            warn(
                f"{rel} is nested more than one level deep; "
                f"using '{parts[0]}' as section, ignoring deeper nesting",
                rel,
            )
        if len(parts) > 1:
            section = _normalize_slug(parts[0])
        if "section" in attrs:
            section = _normalize_slug(str(attrs["section"]))
        if section == "":
            section = None

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

        dedup_key = f"{section or ''}:{slug}"
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

        page = {"slug": slug, "title": title, "content": body, "contentType": content_type}
        if section:
            page["section"] = section
        if "description" in attrs:
            page["description"] = attrs["description"]
        if "draft" in attrs:
            page["draft"] = attrs["draft"]
        if attrs.get("tags"):
            raw_tags = attrs["tags"]
            if not isinstance(raw_tags, list):
                raw_tags = [raw_tags]
            tags = [str(t).lower().strip() for t in raw_tags if str(t).strip()]
            if len(tags) > MAX_TAGS_COUNT:
                error(f"too many tags ({len(tags)}, max {MAX_TAGS_COUNT})", rel)
                valid = False
            for tag in tags:
                if len(tag) > MAX_TAG_LENGTH:
                    error(f'tag "{tag}" exceeds {MAX_TAG_LENGTH} character limit', rel)
                    valid = False
                elif not is_valid_tag(tag):
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

        entries.append((rel, page))

    if not valid:
        sys.exit(1)

    if len(entries) > 5000:
        die(f"{len(entries)} pages exceeds the 5000 page limit")

    print(f"Syncing {len(entries)} page(s) as {content_type}:")
    for rel, page in entries:
        sec = page.get("section")
        if sec:
            print(f"  {rel} to /{content_type}/{sec}/{page['slug']}")
        else:
            print(f"  {rel} to /{content_type}/{page['slug']}")

    if dry_run:
        print("Dry run complete. No changes were made.")
        return

    pages = [page for _, page in entries]
    payload = {"pages": pages, "build": True}
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

    build = data.get("build", {})
    if build.get("error"):
        warn(f"Build was not triggered: {build.get('message') or build['error']}")
    elif build.get("deployUrl"):
        set_output("deploy-url", build["deployUrl"])
        print(f"Deployed to {build['deployUrl']}")


if __name__ == "__main__":
    main()
