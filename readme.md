# Integrations

Official integrations for Sitepaste. Integrations are written in python3 using the stdlib.

## Format and lint

This repo uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting. Run both before committing:

```sh
ruff check .
ruff format .
```

## Actions

- [actions/deploy](actions/deploy) syncs markdown files to Sitepaste and triggers a build.
