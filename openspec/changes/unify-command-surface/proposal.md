## Why

kb-mcp exposes its operations across three surfaces — **MCP tools** (24, for Claude), a personal **REST facade** (9 hand-wired `/api/*` routes), and a **CLI** (admin-only). They already share leaf functions (no business-logic duplication — good), but the *surface definitions* are duplicated and inconsistent:

- Exposing one operation takes **3–4 edits in different spots** (`@mcp.tool` decorator, a `@mcp.custom_route` block, the `post_tools` OpenAPI list, optionally a CLI handler).
- **REST covers only 9** of the operations; the rest (replace, link, preserve, provenance_report, query_data…) have no HTTP endpoint.
- The **OpenAPI spec is a hand-maintained list** (`post_tools`, server.py:1031) with generic `{type: object}` schemas — it drifts and documents nothing useful.
- The **CLI can't run the core operations at all** — no `find`, `get`, `audit` from a terminal/script; it's admin/setup-only.

engraph and Endstate each have **one clean, consistent command contract**. kb-mcp should too — a single source of truth that drives every surface, so the three stay in lockstep and the CLI becomes a first-class way to query the KB.

## What Changes

- New **`commands.py` registry** — one declarative source of truth. Each operation = `{name, leaf_fn, summary, params, surfaces, tier}`.
- **REST routes + OpenAPI derive from the registry** (replaces the hand-wired `/api/*` blocks + the `post_tools` list): every registry op marked `rest` gets `/api/<name>` automatically, and OpenAPI is generated with **per-parameter** docs from the param specs — no drift. Existing route names/behavior preserved.
- **A real CLI over the core operations**, generated from the registry, with **Endstate-style ergonomics**: verb-first `python -m kb_mcp find "query"`, a global `--json` structured envelope, structured error **codes + remediation**, and exit codes (0 ok / 1 error / 2 usage).
- **Shared result/error envelope** (`{success, data, error: {code, message, remediation}}`) used by CLI `--json` and REST.
- **A consistency test** asserting the registry and the live MCP tool set agree (a drift guard, since the MCP decorators stay hand-registered).

Out of scope (future): generating the `@mcp.tool` decorators themselves from the registry (kept hand-registered — rich docstrings, the `note` project-key docstring injection, the tier-2 conditional — reflection would lose fidelity and is too invasive); CLI/REST **auth** changes (CLI stays local-only; REST keeps its API key); streaming; write-op CLI exposure beyond the first ones (the registry makes adding them trivial later).

## Capabilities

### New Capabilities
- `command-surface`: a single operation registry that drives the REST facade, the OpenAPI spec, and a core-operation CLI from one declaration — one consistent contract across MCP ↔ CLI ↔ REST.

## Impact

- Code: new `src/kb_mcp/commands.py` (registry) + `src/kb_mcp/cli_ops.py` (CLI arg→kwargs + envelope); `server.py` REST section refactored to loop the registry; `__main__.py` gains registry-driven core-op subcommands.
- Behavior: REST **expands** from 9 to all registered ops; the existing 9 keep their names + leaf calls. REST + CLI `--json` adopt the shared envelope (the REST facade is personal/new — low blast radius). **MCP tools are unchanged.** CLI gains `find`/`get`/`audit`/`suggest_links`/`provenance_report`/`query_data`/`list_directory` (read/query ops first; clean signatures, safe).
- No new dependencies.
