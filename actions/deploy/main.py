import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NoReturn

API = "https://sitepaste.com/api/v1/public/pages"
TYPES = {"docs", "blog", "standalone"}
IMG_RE = re.compile(r"!\[[^\]]*]\((?!https?://)([^)]+)\)")


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


def slugify(rel_path):
    name = Path(rel_path).stem.lower()
    name = re.sub(r"'", "", name)
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    return name.strip("-")


def titleize(slug):
    return " ".join(w[0].upper() + w[1:] for w in slug.split("-") if w)


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

        body_size = len(body.encode("utf-8"))
        title_size = len(title.encode("utf-8"))

        if body_size > 100_000:
            error(f"content exceeds 100000 byte limit ({body_size} bytes)", rel)
            valid = False
        if len(slug) > 100:
            error(f"slug exceeds 100 character limit ({len(slug)} chars)", rel)
            valid = False
        if title_size > 200:
            error(f"title exceeds 200 byte limit ({title_size} bytes)", rel)
            valid = False
        if attrs.get("description"):
            desc_size = len(attrs["description"].encode("utf-8"))
            if desc_size > 500:
                error(f"description exceeds 500 byte limit ({desc_size} bytes)", rel)
                valid = False

        if slug in slugs:
            error(f'duplicate slug "{slug}", also produced by {slugs[slug]}', rel)
            valid = False
        else:
            slugs[slug] = rel

        for m in IMG_RE.finditer(body):
            warn(
                f'Contains relative image reference "{m.group(1)}". '
                "Upload media separately via the dashboard or POST /api/v1/public/media.",
                rel,
            )

        page = {"slug": slug, "title": title, "content": body, "contentType": content_type}
        if attrs.get("description"):
            page["description"] = attrs["description"]
        if "draft" in attrs:
            page["draft"] = attrs["draft"]
        if attrs.get("tags"):
            tags = attrs["tags"]
            page["tags"] = tags if isinstance(tags, list) else [tags]
        if attrs.get("publishedAt"):
            pa = attrs["publishedAt"]
            page["publishedAt"] = pa + "T00:00:00Z" if is_date_only(pa) else pa

        entries.append((rel, page))

    if not valid:
        sys.exit(1)

    if len(entries) > 5000:
        die(f"{len(entries)} pages exceeds the 5000 page limit")

    print(f"Syncing {len(entries)} page(s) as {content_type}:")
    for rel, page in entries:
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
