# Tasks — Unified command surface

## 1. The registry (TDD first)
- [ ] 1.1 Add `src/kb_mcp/commands.py`: `Param` + `Command` dataclasses and `COMMANDS` tuple
      enumerating the operations with leaf refs, param specs, surfaces, tier. Read/query ops
      (find, get, audit, suggest_links, provenance_report, query_data, list_directory) →
      `{mcp,rest,cli}`; write ops (note, add, edit, replace, link, preserve, reconcile) →
      `{mcp,rest}`.
- [ ] 1.2 Tests `tests/test_commands_registry.py`: every leaf is callable; param specs well-formed;
      positional params at most one per command; names unique; tier-2 ops flagged.

## 2. Shared envelope + arg coercion
- [ ] 2.1 Add `src/kb_mcp/cli_ops.py`: `envelope(success, data=None, error=None)`; `coerce(params,
      raw: dict) -> kwargs` (str/int/bool/list[str] from JSON or CLI strings; reject unknown keys;
      keep the binary-blob guard for text fields); structured `OpError(code, message, remediation)`.
- [ ] 2.2 Tests `tests/test_cli_ops.py`: coercion per type, unknown-key rejection, blob guard,
      envelope shape (success + error).

## 3. REST facade derives from the registry
- [ ] 3.1 Refactor `server.py` REST section: replace the 9 hand-wired `/api/*` blocks with a loop
      over `COMMANDS` (rest) registering a generic handler (gate → body → coerce → threadpool leaf →
      envelope). Honor `KB_MCP_DISABLE_TIER2` for tier-2 ops.
- [ ] 3.2 Generate `/api/openapi.json` from the registry param specs (per-parameter schema +
      summary); delete the `post_tools` hand-list.
- [ ] 3.3 Tests `tests/test_rest_registry.py`: the original 9 routes still exist + call the same
      leaves (back-compat pin); a previously-unexposed op (e.g. replace) now has a route; success →
      `{success:true,data}`, validation error → `{success:false,error:{code,...}}`; OpenAPI lists
      real params; blob guard preserved.

## 4. CLI over the registry
- [ ] 4.1 In `__main__.py`, generate a subparser per `COMMANDS` (cli) op (positional for positional
      params, `--flags` for the rest); global `--json`; dispatch → resolve vault → coerce →
      `cmd.leaf(vault_root, **kwargs)` → human or envelope output; exit codes 0/1/2.
- [ ] 4.2 Keep the existing admin subcommands (init/install-*/backfill-media/*-speaker/serve)
      working unchanged; the generated core-op subcommands are additive.
- [ ] 4.3 Tests `tests/test_cli_core_ops.py`: `find`/`get`/`audit` run against a temp vault, `--json`
      envelope vs human output, missing-arg → exit 2, op error → exit 1 + error code.

## 5. Consistency guard
- [ ] 5.1 Test `tests/test_surface_consistency.py`: every `Command` with `mcp` maps to a live MCP
      tool of the same name whose delegate is the same leaf; fails on drift.

## 6. Docs
- [ ] 6.1 Document the unified surface (one op = MCP tool + REST `/api/<name>` + CLI subcommand) in
      `README.md` / `docs/deployment.md`; show the `--json` envelope + a `curl` and a CLI example.
      Keep `src/kb_mcp/_scaffold/**` + canonical `_Schema/` out of scope (handled separately).

## 7. Verify
- [ ] 7.1 `PYTHONPATH=src KB_MCP_DISABLE_EMBEDDINGS=1 python -m pytest -q` green (no regression).
- [ ] 7.2 `ruff check` clean (no new errors).
- [ ] 7.3 Desk-side smoke: `python -m kb_mcp find "<known term>" --json` returns hits; with
      `KB_MCP_REST_API_KEY` set, `curl -H "Authorization: Bearer $KEY" .../api/replace` works (a
      newly-exposed op) and `/api/openapi.json` lists per-op params.
- [ ] 7.4 `openspec validate unify-command-surface --strict` passes.
