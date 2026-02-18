# Sitepaste Integrations

Official integrations for [Sitepaste](https://sitepaste.com). Integrations are written in JavaScript with no dependencies. Node.js stdlib only.

## Format and lint

This repo uses [oxfmt](https://oxc.rs/docs/guide/usage/formatter.html) for formatting and [oxlint](https://oxc.rs/docs/guide/usage/linter.html) for linting. Run both before committing:

```sh
npx oxfmt --write .
npx oxlint .
```

## Actions

- [actions/deploy](actions/deploy) syncs markdown files to Sitepaste and triggers a build.
