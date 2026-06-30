# Release checklist

kb-mcp is source-first today: users install from a checkout with `uv`. This
checklist keeps that path predictable without pretending the project has a full
PyPI release pipeline yet.

## Versioning policy

The source of truth is `[project].version` in `pyproject.toml`. Tags use
`vX.Y.Z`.

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

## Release steps

1. Update `pyproject.toml`'s version.
2. Update release notes or the GitHub release body with user-visible changes,
   migration notes, and any OpenSpec archives included in the release.
3. Run the pre-release checks above.
4. Commit the version/docs changes.
5. Tag the commit with `vX.Y.Z`.
6. Push the branch and tag.
7. Attach the `dist/` artifacts from `uv build` to the GitHub release if you want
   downloadable packages for that release.

PyPI publishing is deliberately not automated yet. Add it when the project wants
package-index distribution, trusted publishing, and an explicit support contract
for installed versions.
