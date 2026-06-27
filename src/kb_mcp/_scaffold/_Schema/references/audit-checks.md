# Audit checks

Per-check detail for the **audit** (lint) operation — what each check flags, its
severity behaviour, and the proposed fix. SKILL.md § "Audit (lint) checks" lists
the check names; read this when running or acting on an audit. Audit is
read-mostly: the output is a proposal report you review; nothing is rewritten
without explicit confirmation per item or batch.

- **Orphans** — compiled pages with zero inbound links and zero outbound links beyond their `sources` block. Propose: link or archive.
- **Broken wikilinks** — `[[X]]` where `X` does not resolve. The audit skips wikilinks inside fenced code blocks and inline code spans. Bare names resolve against filename stems AND frontmatter `title:` (so date-prefixed sources with a title match are not flagged); a link carrying an explicit non-`.md` extension (`[[…/scan.pdf]]`) resolves if that file exists on disk, matching Obsidian's attachment links. Findings inside append-only trees (`Sources/`, `Evidence/`) — which can't be repaired in place — are surfaced at `info` severity, keeping them out of the actionable `warn` set. Propose: fix path or create stub entity.
- **Supersession integrity** — pages marked `superseded` must have `superseded_by` pointing to a real page; pages marked `active` must not appear as the target of any `superseded_by`.
- **Stale frontmatter** — required fields missing for the page type. Includes: patterns with `project:` (singular) when `projects:` (plural) is the convention for cross-project patterns.
- **`index.md` / `log.md` drift** — files in folders that are not catalogued, catalogue entries pointing to missing files, or `log.md` entries without corresponding artifacts on disk (and vice versa).
- **Unprocessed sources** — `Sources/` files with empty `ingested_into:`, **aged and triaged oldest-first**: each finding carries `meta` (`age_days`, `age_bucket` ∈ fresh <30d / aging <90d / stale, `captured`) and escalates to `warn` once stale. Drain the worst rot first: pick a coherent set of the oldest, call **`propose_compilation(sources=[…])`** for a ready-to-fill scaffold, then compile via **note**.
- **Status / location mismatch** — pages with `status: archived` not living in an `_archive/` subfolder, and vice versa.
- **Unfinished experiments** — experiments with `status: active` and `started` date older than the experiment's `duration` field. Propose: write up results, mark concluded, or extend.
- **Unfinished production lifecycles** — production-logs with `status: recorded` or earlier whose `published` field has been null for >60 days. Propose: update status, fill outcomes, or move to dropped.
- **Stale hubs / snapshots** — research-notes flagged as hub or snapshot with `updated:` older than threshold (default: 90 days for hubs, 30 days for snapshots). Propose: refresh or mark explicitly as historical.
- **Unregistered project key** — pages with a `project:` or `projects:` value not in `_Schema/project-keys.yaml`. Catches drift from Tier 2 `create_file` escape-hatch writes that bypass the auto-register flow. Propose: fix the value via `edit` (frontmatter-patch mode; its typo guard will surface the intended key) or hand-add the new key to the YAML.
- **Embedding drift** — sidecar rows whose row mtime is older than the on-disk file mtime (likely an Obsidian-side edit that bypassed kb-mcp's writer hooks). Propose: run `reconcile` (incremental, stale rows only) or `audit_fix(rebuild_embeddings=true)` (full wipe + rebuild) to refresh.
