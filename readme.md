# Integrations

Official integrations for Sitepaste.

## Format and lint

Sitepaste-owned code is Python and uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```sh
ruff format .
ruff check .
```

Third-party plugins are TypeScript and use [oxlint](https://oxc.rs/docs/guide/usage/linter.html) and [oxfmt](https://oxc.rs/docs/guide/usage/formatter.html). Install dependencies first, then run both:

```sh
npm install
npm run format
npm run lint
```

## Actions

- [actions/deploy](actions/deploy) syncs markdown files to Sitepaste and triggers a build.

## Plugins

- [plugins/obsidian](plugins/obsidian) publish markdown notes to Sitepaste directly from Obsidian.
