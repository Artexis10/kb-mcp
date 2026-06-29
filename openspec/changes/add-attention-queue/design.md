# Design — Attention queue (unified review surface)

## Context

Three measurement-only review queues live in `audit.py`, all returning `AuditFinding`
and orchestrated by `audit(vault_root, *, categories, today)` (one parse pass, then the
selected `_check_*`):

- `_check_stale_review` — emits findings sorted most-dormant-first (ACT-R `activation`
  ascending, `-age_days` tiebreak). `meta` carries `age_days`, `activation`, etc.
- `_check_corpus_contradictions` — emits pairs (`path=A`, `paths=[A,B]`) sorted by
  `cosine + W·dormancy`, cross-family first, capped at `KB_MCP_CONTRADICTION_TOP_N`
  with a trailing summary finding (`path="Knowledge Base/"`, `meta.truncated`).
- `_check_unprocessed_sources` — emits sources with empty `ingested_into`, oldest-first.

The enabling fact: **each check already returns findings in intra-queue rank order**
(emission order == rank). So a composer never recomputes ranks — it enumerates.

## The composition

`attention()` calls `audit()` once with the three categories, then a pure
`_rank(findings, …)` does the rest. Reuse over rebuild: never call the `_check_*`
directly (that would duplicate the parse pass + the ACT-R/env wiring and risk drift).

## Decisions

- **Rank by Reciprocal Rank Fusion over intra-queue position, reusing
  `fusion.reciprocal_rank_fusion_weighted` (k=60, equal weights).** The three queues'
  raw signals are genuinely incomparable (ACT-R `activation` is log-odds and can be
  `-inf`; contradiction `priority ≈ 0.5–1.4`; `age_days` an integer). RRF is
  unit-agnostic by construction — each queue votes purely by rank, which we already
  have. It is the literal idiom `find` uses, and it is parameter-light (one constant).
  - *Rejected — normalize-to-urgency:* requires inventing a per-queue 0–1 transform;
    min-max is population-unstable and breaks on `-inf`, a sigmoid needs hand-tuned
    params. Manufacturing a cross-queue comparable magnitude is the closest of the
    options to *inference* and the hardest to defend on the pure-substrate line.
  - *Rejected — round-robin/quota:* effectively unweighted RRF minus the one property
    that makes RRF valuable here (below); quotas are themselves arbitrary policy.
- **Multi-signal additivity is the decisive property.** A note flagged by two queues
  (stale AND a contradiction anchor) accumulates `1/(k+r₁) + 1/(k+r₂)`, strictly above
  any single-membership score in its tier — so doubly-flagged notes rise automatically.
  That is exactly the "did I conclude this is stale *and* it sits next to a conflicting
  note?" case the surface most wants on top. It is counting independent deterministic
  votes — measurement, not judgment.
- **Dedup by anchor `path` into one item carrying `reasons[]`.** Additivity *requires*
  dedup to express "flagged twice," and a reviewer thinks per-note. The contradiction
  pair is not lost: its reason keeps `related_paths=[A,B]` + full `meta`. A pair
  surfaces under anchor `A` (the sorted-first path the check already emits); `B` is an
  independent item only if separately flagged — a faithful 1:1 with the contradiction
  queue (the rejected "explode the pair into two items" would double-count it). Within
  one category an anchor's score uses its **best** rank (the fusion util's standard
  per-list dedup), but **all** its reasons are attached — so "A overlaps both B and C"
  lists two reasons without a prolific anchor dominating the score.
- **Equal default weights + a fixed tiebreak `corpus_contradictions > stale_review >
  unprocessed_source`.** With equal weights the order is a clean rank-major,
  category-minor interleave except multi-flagged anchors jump up; the score stays
  purely rank-driven (trivial to explain) and the cross-queue preference is a
  transparent documented tiebreak, not a magic float. Per-category weights remain a
  code seam (not env-exposed in v1, YAGNI). `k=60` is the `fusion` default.
- **Drop and fold the contradiction summary finding.** The trailing
  `corpus_contradictions` finding (`meta.truncated`) is not a reviewable item; filter
  it out before ranking and fold its count into `upstream_truncated`. The surface
  reports both its own `truncated` (items beyond `limit`) and `upstream_truncated`
  (pairs `audit` itself capped) in an explicit `note` — never a silent truncation,
  mirroring the contradiction queue's own "N more not shown" discipline.
- **Two params only (YAGNI):** `categories` (optional subset of the three, validated
  against them with a clear `ValueError`) and `limit` (default 25). `project` scoping is
  cut for v1 — findings don't carry the note's project field, so it would mean threading
  a filter through `audit()` and all three checks. `today` is threaded internally for
  test determinism but not exposed as a command param (matching `op_audit`).

## Pure-substrate justification

Every item's rank is a deterministic arithmetic function of (a) the intra-queue rank
each measurement-only check already computed and (b) a fixed RRF formula with constant
`k` and constant weights. At attention time no note content is read, embedded, or
compared; no cross-item semantic judgment is made. This is the same machinery and the
same status as `find`'s weighted RRF and the contradiction queue's dormancy sort — both
already in bounds. The per-item `proposed_fix` states the ranking is "a deterministic
measurement, not a judgment that anything conflicts or is wrong," enumerates the
human/Claude actions (keep / `replace` / `reconcile` / `propose_compilation` / archive),
and says nothing is auto-acted. A server-side LLM reasoning across the surfaced items to
decide what is actually wrong would be the out-of-bounds step — attention stops short.

## Risks

- **Schema-fidelity fixture must be regenerated.** Adding any command breaks
  `tests/test_mcp_schema_fidelity.py` until `tests/fixtures/mcp_tool_schemas.json` is
  regenerated. Mitigated by the new `scripts/dump-tool-schemas.py` (serializes the live
  schema via the same path the test uses), so the regen is reproducible, not hand-edited.
- **Two-stage truncation.** `attention`'s `limit` cannot surface contradiction pairs
  that `audit` already capped upstream; this is reported via `upstream_truncated` + the
  `note` clause rather than raising the upstream cap. Acceptable: the surface is honest
  about what it can't show and points at the env knob.
- **Tool ambiguity vs `audit`.** Both read the KB. The `attention` description leads
  with "your review queue / front door for daily review" and explicitly defers the full
  lint/health report to `audit`, so natural-language tool selection routes correctly.
