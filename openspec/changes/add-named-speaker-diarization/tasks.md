# Tasks — Named-speaker diarization

## 1. Ported pure-NumPy core (TDD first — no torch)
- [ ] 1.1 Add `src/kb_mcp/speaker_attribution.py`: `attribute_clusters(cluster_embeddings,
      first_onset, profiles, *, margin=0.05, merge_threshold=0.50, confident_delta=0.15,
      rel_gap=0.10) -> dict[cluster_id, Attribution]` (port from Q; cosine + margin/standout
      rules; unmatched → stable `Speaker A/B…` by first-onset order).
- [ ] 1.2 Add `src/kb_mcp/speaker_assignment.py`: `assign_span(start, end, turns) -> label|None`
      (max-overlap, earliest-turn tiebreak) + average-linkage cluster merge helper.
- [ ] 1.3 Unit tests `tests/test_speaker_attribution.py` + `tests/test_speaker_assignment.py`:
      threshold/margin/standout table, ambiguous→anonymous, over-split merge, max-overlap +
      tiebreak, determinism. All torch-free, run under the default test env.

## 2. Voice-profile store
- [ ] 2.1 Add `src/kb_mcp/voice_profiles.py`: JSON store at the operational sidecar dir
      (`load_profiles()`, `save_profile(name, centroid, *, threshold, is_self)`,
      `remove_profile(name)`, `list_profiles()`); multi-sample running-average centroid;
      schema `{name: {centroid, threshold, samples, is_self, updated}}`.
- [ ] 2.2 Tests `tests/test_voice_profiles.py`: create/list/remove, multi-sample averaging,
      store location is NOT under the vault note trees, corrupt/missing file → empty store.

## 3. Voice embedding (soft-fail seam)
- [ ] 3.1 Add `src/kb_mcp/voice_embed.py`: lazy speechbrain ECAPA singleton;
      `embed_spans(audio_path, spans) -> np.ndarray (192,)`; TF32 disabled; `_voice_device()`
      returns CPU when ASR/whisper active (CLIP precedent) with `KB_MCP_VOICE_DEVICE` override;
      soft-import seam so a box without `speechbrain` raises ImportError caught upstream.
- [ ] 3.2 Tests with the model patched: device selection, TF32 disabled, ImportError → None.

## 4. Wire attribution into extraction
- [ ] 4.1 In `extract._diarize`: after anonymous turns, when ≥1 profile enrolled, embed clusters
      → merge → `attribute_clusters` → relabel via `assign_span`; render `[<name>]: …` +
      structured `speakers` names. Guard: no profiles OR soft-fail → today's anonymous output.
- [ ] 4.2 Ensure `media_worker._run_extraction` + `preserve.update_sidecar_*` carry resolved
      names through unchanged (no sidecar schema change).
- [ ] 4.3 Tests `tests/test_diarize_named.py` (pyannote + ECAPA patched): enrolled→named,
      unknown→anonymous, no-profiles→byte-identical to anonymous, soft-fail→anonymous.

## 5. CLI enrollment
- [ ] 5.1 Add `src/kb_mcp/enroll_speaker.py` + register `enroll-speaker`/`list-speakers`/
      `remove-speaker` subcommands in `src/kb_mcp/__main__.py` (beside install-hook/skill).
      `--self` sets is_self; enroll averages across repeated `--name`.
- [ ] 5.2 Tests `tests/test_enroll_speaker_cli.py` (embedder patched): enroll writes a profile,
      `--self` flag, list/remove round-trip.

## 6. Deps + docs
- [ ] 6.1 Add `speechbrain>=1.0` to the `diarization` extra in `pyproject.toml`; note the ECAPA
      model + `HUGGINGFACE_TOKEN` in the extra's comment.
- [ ] 6.2 Update the SKILL/scaffold media docs to mention named speakers (generic; leak-guard
      green) and `KB_MCP_VOICE_*` env vars in the deployment/README notes. Keep scaffold generic.

## 7. Verify
- [ ] 7.1 `PYTHONPATH=src KB_MCP_DISABLE_EMBEDDINGS=1 uv run python -m pytest -q` green
      (full suite, no regression).
- [ ] 7.2 `ruff check` clean.
- [ ] 7.3 Desk-side smoke (GPU box): enroll own voice from a sample, diarize a 2-speaker
      recording, confirm `[<name>]:` for the enrolled voice + anonymous for the other, and
      that the transcript is findable by the enrolled name.
- [ ] 7.4 `openspec validate add-named-speaker-diarization --strict` passes.
