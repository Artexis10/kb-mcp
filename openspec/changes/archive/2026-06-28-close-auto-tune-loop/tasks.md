# Tasks — Close the auto-tune loop

## 1. find.py — adopted-config (de)serialization + load seam (TDD)

- [x] 1.1 Add `ranking_config_to_jsonable(cfg) -> dict` (`dataclasses.asdict`) and
      `ranking_config_from_jsonable(d) -> RankingConfig` (field-driven over
      `dataclasses.fields`: coerce int/float; coerce the four `intent_weights_*` to
      length-`len(LANE_ORDER)` float tuples with a length assert; ignore unknown
      keys; default missing keys).
- [x] 1.2 Add `_REPO_ROOT = Path(__file__).resolve().parents[2]`,
      `_load_adopted_ranking() -> RankingConfig` (resolution: disable-flag → env
      path → repo-root `ranking_config.json` → DEFAULT; malformed/bad-type/bad-tuple
      → `log.error` + DEFAULT), a per-process memo `_active_ranking()`, and
      `reset_active_ranking_cache()`.
- [x] 1.3 Change the `find()` seam: `config or DEFAULT_RANKING` →
      `config if config is not None else _active_ranking()`.
- [x] 1.4 `tests/conftest.py`: add `monkeypatch.setenv("KB_MCP_DISABLE_RANKING_CONFIG",
      "1")` to the autouse fixture so a committed file never pollutes the suite.
- [x] 1.5 `tests/test_ranking_config_load.py`: absent→DEFAULT; valid file (via
      `KB_MCP_RANKING_CONFIG`)→loaded with tuples coerced; malformed JSON→DEFAULT +
      error log; unknown knob ignored + missing knob defaulted; bad intent-tuple
      length→DEFAULT; env path override honored; disable-flag→DEFAULT even with a
      file; memo + `reset_active_ranking_cache()`.
- [x] 1.6 Extend `tests/test_ranking_config.py`: `to_jsonable→json→from_jsonable ==
      DEFAULT` (and a tuned config) with intent fields surviving as tuples;
      reversibility — env-adopt a non-default file changes `find()` output, remove +
      reset → DEFAULT path. (Existing `find(no config) == find(config=DEFAULT)`
      invariant still holds under the conftest disable flag.)

## 2. derive_relevance_pairs.py — idempotent snapshot (TDD)

- [x] 2.1 Extract `mine_pairs(window_seconds, *, write, logs_dir=LOGS) -> list[dict]`
      from `main()`; keep the CLI, `--dry-run`, and the golden-additions proposal.
- [x] 2.2 Switch the write to an atomic deduped snapshot (tmp sibling + `os.replace`,
      mode `w`) keyed by `(query, cited_path)` keeping best confidence — not append.
- [x] 2.3 `tests/test_derive_relevance_pairs.py`: snapshot idempotency (two runs over
      the same fixture logs → identical bytes, no dupes); no `.tmp` residue.

## 3. auto_tune_ranking.py — combined objective + candidate/report + adopt (TDD)

- [x] 3.1 Add `EPSILON = 0.01`, `MIN_PAIRS = 8`, `CONF_MIN = 0.25` consts + CLI flags.
- [x] 3.2 `pairs_to_eval(pairs, golden_queries, *, conf_min) -> list[dict]`: dedup
      golden-overlapping queries, apply `CONF_MIN`, group to `{query, relevant:set}`
      (binary).
- [x] 3.3 `pair_mrr(ranked_by_query, eligible)` (+ `pair_recall10` for the report) —
      reuse `find()` + `_canon` via a small `rank_queries()` helper in
      `eval_retrieval.py`.
- [x] 3.4 `build_combined_evaluate_fn(...)` → lexicographic `combined_score`:
      `(-1.0,g)` floor / `(0.0,g)` guard / `(pair_mrr,g)` per the design.
- [x] 3.5 `write_candidate(path, cfg, meta)` + `write_report(path, default_cfg,
      best_cfg, meta)` (atomic); meta carries `baseline_golden`, `candidate_golden`,
      `pair_mrr`, `pair_recall10`, `n_eligible_pairs`, `guard_active`, `window_hours`.
- [x] 3.6 `adopt(candidate_path, target_path, *, force, epsilon)`: validate-load,
      refuse when `candidate_golden < baseline_golden - EPSILON` unless `force`,
      atomic copy of the RAW config to repo-root `ranking_config.json`, print
      git-commit + restart steps.
- [x] 3.7 `main()`: mine fresh first (import `mine_pairs`) → load golden → pairs_to_eval
      → measure baseline → `optimize(combined)` → write candidate + report; `--adopt`
      branch. Tuple-score selection (no float print of the score).
- [x] 3.8 Extend `tests/test_auto_tune.py`: `pairs_to_eval` dedup/filter; binary
      `pair_mrr` independent of confidence value; `combined_score` + `optimize` floor
      blocks a golden-regressing candidate; `MIN_PAIRS` guard reduces to golden-only;
      lexicographic golden tiebreak; candidate + report shape; adopt floor gate.

## 4. Docs

- [x] 4.1 `docs/ranking-tuning.md`: the loop (mine → tune → review report → adopt
      [commit + restart] → revert) + the three env vars
      (`KB_MCP_RANKING_CONFIG`, `KB_MCP_DISABLE_RANKING_CONFIG`, and the existing
      `KB_MCP_DISABLE_EMBEDDINGS` for desk-side runs).

## 5. Verify

- [x] 5.1 `PYTHONPATH=src KB_MCP_DISABLE_EMBEDDINGS=1 uv run python -m pytest -q`
      green (765 passed, 5 skipped torch/PIL-gated; the one collection error is the
      pre-existing torch-hard-import in `tests/test_voice_embed.py`, a diarization
      test that needs the embeddings extra — unrelated to this change).
- [x] 5.2 `uvx ruff check` clean on changed files (no new findings vs `origin/main`;
      the repo's lint is advisory with a known baseline).
- [x] 5.3 `openspec validate close-auto-tune-loop --strict` passes.
- [x] 5.4 Live-vault smoke (2026-06-28/29, on the GPU box). VALIDATED: mining on the
      real logs (queries.jsonl 822KB) → 21 pairs + idempotent snapshot; the loop
      ENGAGES on real signal — 10 distinct eligible queries (≥ MIN_PAIRS=8), guard OFF
      (overturned the earlier "no-op until usage compounds" expectation); end-to-end
      run with the new code clean. DEFERRED: the full coordinate descent did not
      converge to a candidate in practical wall-time on the live vault even with the
      `scope="kb-only"` eval speedup — the per-`find()` eval over the large KB tree is
      the floor (~70 CPU-min, no candidate). So `--adopt` of a tuned `ranking_config.json`
      awaits either a long unattended run or an eval-harness perf pass (follow-on). The
      adopted-config seam itself is shipped + default-off; deploy (`reset --hard` +
      restart) is the maintainer's step.
