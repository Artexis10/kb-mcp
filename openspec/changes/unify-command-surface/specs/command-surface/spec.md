## ADDED Requirements

### Requirement: Single Command Registry Is The Source Of Truth

The system SHALL define a single declarative command registry (`commands.py`) that enumerates each
exposed operation with its name, leaf function, summary, parameter specs, and the surfaces it is
exposed on. The REST facade, the OpenAPI document, and the core-operation CLI SHALL all be derived
from this registry — no surface may maintain its own separate list of operations.

#### Scenario: One entry exposes an op across surfaces

- **WHEN** a new operation is added as a single registry entry with surfaces `{mcp, rest, cli}`
- **THEN** its `/api/<name>` REST route, its OpenAPI path, and its CLI subcommand all exist without
  any further per-surface edits
- **AND** removing the entry removes it from all derived surfaces

#### Scenario: Registry agrees with the MCP tool set

- **WHEN** the consistency test runs
- **THEN** every registry command marked `mcp` corresponds to a live MCP tool of the same name whose
  delegate is the same leaf callable
- **AND** the test fails if the registry and the registered MCP tools drift apart

### Requirement: REST Facade And OpenAPI Derive From The Registry

The REST facade SHALL register an `/api/<name>` POST route for every registry command exposed on the
`rest` surface, using one generic handler (auth gate → JSON body → coerced leaf kwargs → threadpool
call → envelope). The OpenAPI document SHALL be generated from the registry's parameter specs with
per-parameter schemas, replacing the hand-maintained tool list.

#### Scenario: Existing REST routes are preserved

- **WHEN** the registry-driven facade is built
- **THEN** the previously hand-wired routes (find, get, note, add, edit, audit, reconcile,
  list_directory, suggest_links) still exist at the same paths and call the same leaf functions
- **AND** operations that previously lacked a route (e.g. replace, link, provenance_report) now have
  one because they are in the registry with `rest`

#### Scenario: OpenAPI documents real parameters

- **WHEN** `GET /api/openapi.json` is requested
- **THEN** each path's request schema lists the operation's actual parameters (name, type, required)
  from the registry, not a generic `{type: object}`
- **AND** no separate hand-maintained operation list exists to drift

### Requirement: Core-Operation CLI With Consistent Ergonomics

The CLI SHALL expose every registry command on the `cli` surface as a verb-first subcommand
(`python -m kb_mcp <name> …`), with positional arguments for params marked positional and `--flags`
for the rest. It SHALL support a global `--json` flag selecting a structured envelope, emit
structured error codes with remediation, and return exit code 0 on success, 1 on operation error,
and 2 on usage/argument error.

#### Scenario: Query the KB from the terminal

- **WHEN** `python -m kb_mcp find "carbonation rig" --json` is run
- **THEN** the search runs against the local vault and the results are printed as a single-line JSON
  envelope `{success: true, data: [...]}`
- **AND** exit code is 0

#### Scenario: Human-readable default and usage errors

- **WHEN** the same command is run without `--json`
- **THEN** the results are printed in a human-readable form (no envelope wrapper)
- **AND** running it with a missing required argument prints `Error [..]: …` and exits 2

### Requirement: Shared Result And Error Envelope

The CLI (`--json` mode) and the REST facade SHALL use one shared envelope shape:
`{success, data, error: {code, message, remediation}}`. A success carries `data` with `success:true`
and no `error`; a failure carries `success:false` and an `error` block with a stable `code`.

#### Scenario: Error envelope carries a stable code

- **WHEN** an operation fails validation (e.g. a bad argument) in REST or CLI `--json` mode
- **THEN** the response is `{success: false, error: {code, message, remediation}}` with a stable,
  machine-readable `code`
- **AND** the same logical failure yields the same `code` on both surfaces

#### Scenario: Binary-blob guard is preserved

- **WHEN** a REST request passes an oversized base64 blob in a text field
- **THEN** it is rejected with the existing `BINARY_BLOB_REJECTED`-class error, as before this change
