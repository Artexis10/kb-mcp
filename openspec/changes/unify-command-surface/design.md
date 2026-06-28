# Design — Unified command surface

## Context

Three surfaces, one set of leaf functions, but the *surface wiring* is hand-maintained per
surface (server.py MCP decorators + REST routes + `post_tools` OpenAPI list; `__main__.py` CLI).
The leaf functions (`find_module.find`, `note_module.note`, …) already take `vault_root` + kwargs
and return plain dicts/dataclasses — so a single declaration per operation can drive every surface.

## Goals / non-goals

- **Goal:** one declarative registry as the source of truth for REST + OpenAPI + CLI; a real CLI
  for the core ops with Endstate-style ergonomics; no surface drift.
- **Non-goal:** regenerating the `@mcp.tool` decorators (they stay hand-registered — rich
  docstrings, `note`'s runtime project-key docstring, the tier-2 conditional). Instead a test
  asserts the registry agrees with the live MCP tool set.
- **Non-goal:** auth changes (CLI local-only; REST keeps `KB_MCP_REST_API_KEY`), streaming, and
  exposing every write op via CLI in this change.

## The registry (`commands.py`)

```python
@dataclass(frozen=True)
class Param:
    name: str
    type: str            # "str" | "int" | "bool" | "list[str]"
    required: bool = False
    help: str = ""
    cli_positional: bool = False   # first positional arg in the CLI (e.g. find's query, get's path)

@dataclass(frozen=True)
class Command:
    name: str            # canonical op name, identical across surfaces
    leaf: Callable       # the leaf function (called as leaf(vault_root, **kwargs))
    summary: str
    params: tuple[Param, ...]
    surfaces: frozenset  # subset of {"mcp", "rest", "cli"}
    tier: int = 1
```

`COMMANDS: tuple[Command, ...]` enumerates the operations. Read/query ops (`find`, `get`, `audit`,
`suggest_links`, `provenance_report`, `query_data`, `list_directory`) get `{"mcp","rest","cli"}`;
write ops (`note`, `add`, `edit`, `replace`, `link`, `preserve`, `reconcile`) get `{"mcp","rest"}`
for now (CLI deferred — registry makes it a one-line flip later). `surfaces` carries `"mcp"` only
as the consistency-check anchor; it does NOT register the MCP tool (those stay hand-wired).

## Decisions

- **Registry drives REST, not MCP.** A loop over `COMMANDS` with `"rest"` registers
  `@mcp.custom_route("/api/<name>", POST)` using one generic handler: gate → parse JSON body →
  coerce body to leaf kwargs via the `Param` specs → `run_in_threadpool(cmd.leaf, vault_root, **kwargs)`
  → envelope. This replaces the 9 hand-wired blocks and expands coverage. The existing 9 names +
  their leaf calls are preserved (a back-compat test pins them).
- **OpenAPI is generated** from the `Param` specs — real per-parameter schemas + the summary, not
  `{type: object}`. Kills the `post_tools` hand-list and its drift.
- **CLI is generated** from `COMMANDS` with `"cli"`. `argparse` subparser per op; `cli_positional`
  params become positionals (`find "query"`, `get <path>`), the rest become `--flags`
  (`list[str]` → repeatable or comma-split; `bool` → store_true). Endstate ergonomics:
  - global `--json` → single-line envelope to stdout; default → human-readable.
  - structured errors: `Error [CODE]: message` + remediation (human) / envelope `error` block (json).
  - exit codes: 0 ok, 1 op error, 2 usage/arg error.
  - CLI is **local-only** (already has vault filesystem access; no auth needed), matching today.
- **Shared envelope** (`cli_ops.envelope`): `{success, data, error: {code, message, remediation}}`,
  mirroring Endstate. REST 200 wraps results as `{success: true, data: …}`; REST 4xx as
  `{success: false, error: {…}}`. The REST facade is personal + new, so adopting the envelope is a
  low-risk contract improvement (documented as the one behavior change).
- **Wide signatures (`note`, 20+ args):** the registry `params` lists the *exposed* set (the common
  fields); type-specific extras stay reachable via MCP. CLI scope for writes is deferred anyway, so
  REST keeps full kwargs pass-through for them.
- **Consistency guard:** a test asserts every `Command` with `"mcp"` exists as a live MCP tool and
  its `leaf` is the same callable the MCP tool delegates to — so the registry can't silently drift
  from the real tool set.

## Risks

- The REST refactor must be **behavior-preserving** for the existing 9 routes — pinned by a
  before/after test (same status codes, same leaf calls, same result payloads under the envelope).
- Body→kwargs coercion must reject unknown/oversized fields the way the hand-written handlers did
  (keep the `BINARY_BLOB_REJECTED` guard for text fields).
- `query_data`/`list_directory` are tier-2 (opt-out via `KB_MCP_DISABLE_TIER2`) — the registry
  honors the same flag for their REST/CLI exposure.
