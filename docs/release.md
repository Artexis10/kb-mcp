# Release checklist

kb-mcp is source-first today: users install from a checkout with `uv`. Release
Please manages version bumps, `CHANGELOG.md`, tags, and GitHub Releases. PyPI
publishing is intentionally not automated yet.

## Versioning policy

The source of truth is `[project].version` in `pyproject.toml`, updated by
Release Please. Tags use `vX.Y.Z`.

While the project is pre-1.0 (`0.y.z`):

- Bump **minor** for new public CLI/MCP/REST behavior, vault-schema changes, or
  compatibility changes a user might need to notice.
- Bump **patch** for bug fixes, docs, packaging polish, CI, sample-vault updates,
  and implementation changes that do not alter the public surface.
- Call out breaking pre-1.0 changes in the release notes even when they are
  represented as a minor bump.

After `1.0.0`, use standard SemVer:

- **MAJOR** for incompatible changes to public CLI/MCP/REST behavior, stored
  vault conventions, or required environment semantics.
- **MINOR** for additive public behavior.
- **PATCH** for compatible fixes and docs.

## Pre-release checks

Run from the repo root:

```bash
uv sync
uv run python -m pytest -q
uvx ruff check .
npm exec --yes @fission-ai/openspec -- validate --specs --strict
uv run python scripts/smoke-sample-vault.py
uv run python -m kb_mcp doctor --vault examples/sample-vault --profile lean
uv build
```

Optional host-specific checks:

```bash
uv run python -m kb_mcp doctor --profile hybrid
uv run python -m kb_mcp doctor --profile media
uv run python -m kb_mcp doctor --profile remote
```

Run the optional checks only on machines configured for those profiles. `media`
expects the media extra plus Tesseract; `remote` expects OAuth and public-url
environment variables.

## Commit convention

Release Please reads Conventional Commit messages after the latest release tag:

- `fix: ...` -> patch release
- `feat: ...` -> minor release
- `feat!: ...` or a `BREAKING CHANGE:` footer -> major release

Use scopes when helpful, for example `feat(doctor): ...` or
`fix(media): ...`. `docs:`, `ci:`, and `chore:` are hidden from the public
changelog by default and do not drive releases unless they include a breaking
marker.

## Release flow

1. Merge feature/fix PRs to `main` using Conventional Commit titles.
2. Release Please opens or updates a release PR that bumps `pyproject.toml`,
   `.release-please-manifest.json`, and `CHANGELOG.md`.
3. Confirm CI and the pre-release checks above.
4. Merge the Release Please PR.
5. Release Please tags `vX.Y.Z` and creates the GitHub Release.
6. The release workflow builds `dist/` with `uv build` and uploads the wheel/sdist
   to the GitHub Release.

The initial `0.1.0` baseline is recorded in `.release-please-manifest.json` and
`CHANGELOG.md`; future releases should come from Release Please rather than
manual version edits. Add PyPI publishing when the project wants package-index
distribution, trusted publishing, and an explicit support contract for installed
versions.
