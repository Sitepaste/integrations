const fs = require('node:fs');
const path = require('node:path');

const API = 'https://sitepaste.com/api/v1/public/pages';
const TYPES = new Set(['docs', 'blog', 'standalone']);

const input = (name) =>
  (process.env[`INPUT_${name.toUpperCase()}`] || '').trim();
const output = (name, value) => {
  const file = process.env.GITHUB_OUTPUT;
  if (file) fs.appendFileSync(file, `${name}=${value}\n`);
};
const fail = (msg, file) => console.log(file ? `::error file=${file}::${msg}` : `::error::${msg}`);
const warn = (msg, file) =>
  console.log(file ? `::warning file=${file}::${msg}` : `::warning::${msg}`);
const byteLen = (s) => Buffer.byteLength(s, 'utf8');

function stripQuotes(s) {
  if (s.length >= 2 && (s[0] === '"' || s[0] === "'") && s[s.length - 1] === s[0]) {
    return s.slice(1, -1);
  }
  return s;
}

function stripCR(line) {
  return line.endsWith('\r') ? line.slice(0, -1) : line;
}

function isDateOnly(s) {
  if (s.length !== 10 || s[4] !== '-' || s[7] !== '-') return false;
  for (let i = 0; i < 10; i++) {
    if (i === 4 || i === 7) continue;
    if (s[i] < '0' || s[i] > '9') return false;
  }
  return true;
}

function parseFrontMatter(raw) {
  const lines = raw.split('\n');
  if (stripCR(lines[0]) !== '---') return { attrs: {}, body: raw };
  let close = -1;
  for (let i = 1; i < Math.min(lines.length, 31); i++) {
    if (stripCR(lines[i]) === '---') {
      close = i;
      break;
    }
  }
  if (close === -1) return { attrs: {}, body: raw };
  const attrs = {};
  for (let i = 1; i < close; i++) {
    const line = stripCR(lines[i]);
    const sep = line.indexOf(': ');
    if (sep === -1) continue;
    const key = line.slice(0, sep).trim();
    let val = line.slice(sep + 2).trim();
    if (val === 'true') val = true;
    else if (val === 'false') val = false;
    else if (val.startsWith('[') && val.endsWith(']')) {
      const inner = val.slice(1, -1).trim();
      val = inner ? inner.split(',').map((s) => stripQuotes(s.trim())) : [];
    } else {
      val = stripQuotes(val);
    }
    attrs[key] = val;
  }
  return { attrs, body: lines.slice(close + 1).join('\n') };
}

function slugify(name) {
  return path
    .basename(name, path.extname(name))
    .toLowerCase()
    .replace(/'/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-|-$/g, '');
}

function titleize(slug) {
  return slug
    .split('-')
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

class AbortError extends Error {}
function fatal(msg, file) {
  fail(msg, file);
  process.exitCode = 1;
  throw new AbortError();
}

(async () => {
  try {
    const token = input('api-token');
    const dir = input('content-dir') || 'content';
    const type = input('content-type') || 'docs';
    const siteId = input('site-id');
    const dryRun = input('dry-run') === 'true';

    if (token) console.log(`::add-mask::${token}`);

    if (!token) fatal('api-token is required, set it as a secret in your repository settings');
    if (!TYPES.has(type))
      fatal(`invalid content-type "${type}", must be one of docs, blog, or standalone`);

    let dirEntries;
    try {
      dirEntries = fs.readdirSync(dir, { recursive: true, withFileTypes: true });
    } catch (e) {
      fatal(`could not read directory "${dir}": ${e.message}`); // throws, dirEntries always assigned past here
    }

    const files = [];
    for (const ent of dirEntries) {
      if (!ent.isFile() || !ent.name.endsWith('.md')) continue;
      const parent = ent.parentPath;
      const full = path.join(parent, ent.name);
      const rel = path.relative(dir, full);
      if (rel.split(path.sep).some((s) => s.startsWith('.'))) continue;
      files.push({ full, rel });
    }

    if (!files.length) {
      warn(`No markdown files found in ${dir}.`);
      return;
    }

    const entries = [];
    const slugs = new Map();
    let valid = true;

    for (const file of files) {
      const raw = fs.readFileSync(file.full, 'utf8');
      const { attrs, body } = parseFrontMatter(raw);
      const slug = attrs.slug || slugify(file.rel);
      const title = attrs.title || titleize(slug);

      const bodySize = byteLen(body);
      const titleSize = byteLen(title);
      if (bodySize > 100_000) {
        fail(`content exceeds 100000 byte limit (${bodySize} bytes)`, file.rel);
        valid = false;
      }
      if (slug.length > 100) {
        fail(`slug exceeds 100 character limit (${slug.length} chars)`, file.rel);
        valid = false;
      }
      if (titleSize > 200) {
        fail(`title exceeds 200 byte limit (${titleSize} bytes)`, file.rel);
        valid = false;
      }
      if (attrs.description) {
        const descSize = byteLen(attrs.description);
        if (descSize > 500) {
          fail(`description exceeds 500 byte limit (${descSize} bytes)`, file.rel);
          valid = false;
        }
      }

      if (slugs.has(slug)) {
        fail(`duplicate slug "${slug}", also produced by ${slugs.get(slug)}`, file.rel);
        valid = false;
      } else {
        slugs.set(slug, file.rel);
      }

      // Matches ![alt](path) where path is not an absolute URL.
      let m;
      const imgRe = /!\[[^\]]*]\((?!https?:\/\/)([^)]+)\)/g;
      while ((m = imgRe.exec(body))) {
        warn(
          `Contains relative image reference "${m[1]}". Upload media separately via the dashboard or POST /api/v1/public/media.`,
          file.rel,
        );
      }

      const page = { slug, title, content: body, contentType: type };
      if (attrs.description) page.description = attrs.description;
      if ('draft' in attrs) page.draft = attrs.draft;
      if (attrs.tags) page.tags = Array.isArray(attrs.tags) ? attrs.tags : [attrs.tags];
      if (attrs.publishedAt) {
        page.publishedAt = isDateOnly(attrs.publishedAt)
          ? attrs.publishedAt + 'T00:00:00Z'
          : attrs.publishedAt;
      }

      entries.push({ rel: file.rel, page });
    }

    if (!valid) {
      process.exitCode = 1;
      return;
    }

    if (entries.length > 5000) fatal(`${entries.length} pages exceeds the 5000 page limit`);

    console.log(`Syncing ${entries.length} page(s) as ${type}:`);
    for (const e of entries) {
      console.log(`  ${e.rel} to /${type}/${e.page.slug}`);
    }

    if (dryRun) {
      console.log('Dry run complete. No changes were made.');
      return;
    }

    const pages = entries.map((e) => e.page);
    const payload = { pages, build: true };
    if (siteId) payload.siteId = siteId;

    let res;
    try {
      res = await fetch(API, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(120_000),
      });
    } catch (e) {
      fatal(
        e.name === 'TimeoutError'
          ? 'request timed out after 120 seconds'
          : `request failed: ${e.message}`,
      );
    }

    let data;
    try {
      data = await res.json();
    } catch {
      data = {};
    }

    if (!res.ok) {
      if (res.status === 400 && data.pages) {
        for (const [idx, errors] of Object.entries(data.pages)) {
          const file = entries[Number(idx)]?.rel || `page ${idx}`;
          for (const [field, msg] of Object.entries(errors)) {
            fail(`validation failed for ${field}: ${msg}`, file);
          }
        }
      } else {
        fail(`api returned ${res.status}: ${data.error || 'unknown error'}`);
      }
      process.exitCode = 1;
      return;
    }

    output('page-count', pages.length);
    console.log(`Synced ${pages.length} page(s) successfully.`);
    if (data.build?.error) {
      warn(`Build was not triggered: ${data.build.message || data.build.error}`);
    } else if (data.build?.deployUrl) {
      output('deploy-url', data.build.deployUrl);
      console.log(`Deployed to ${data.build.deployUrl}`);
    }
  } catch (e) {
    if (!(e instanceof AbortError)) throw e;
  }
})();
