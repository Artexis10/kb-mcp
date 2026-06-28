# Tasks — Diarization CPU-torch sidecar

## 1. Sidecar uv project (pinned, validated empirically)
- [x] 1.1 Add `sidecar/diarizer/pyproject.toml`: standalone uv project (`[tool.uv] package=false`),
      explicit CPU torch index, load-bearing pins `pyannote.audio>=3.1,<3.2` / `torch>=2.2,<2.3` /
      `torchaudio>=2.2,<2.3` / `speechbrain>=0.5.16,<1` / `huggingface_hub>=0.19,<0.26` /
      `numpy<2` / `faster-whisper<1.1` / `requests` (Python `>=3.11,<3.13`).
- [x] 1.2 `uv lock` → commit `sidecar/diarizer/uv.lock`; resolved pyannote 3.1.1 / torch 2.2.2+cpu /
      torchaudio 2.2.2+cpu / speechbrain 0.5.16 / huggingface_hub 0.25.2, no torchcodec.
- [x] 1.3 Add `sidecar/diarizer/worker.py`: standalone (no `kb_mcp` import); stdout→stderr; decode
      via faster-whisper `decode_audio`; load pyannote (`token=`/`use_auth_token=` fallback); write
      `{"turns":[…]}` UTF-8 JSON to the out-file; clear nonzero-exit error on a gated/unloadable
      pipeline.
- [x] 1.4 `uv sync` the sidecar + import smoke (`AudioMetaData` / `list_audio_backends` / `Pipeline`
      / `decode_audio` all import) + worker run on a synthetic sine WAV: decodes, reaches the gated
      model, exits cleanly nonzero without a token (the soft-fail boundary). All seven walls cleared.

## 2. Subprocess seam in extraction (TDD)
- [x] 2.1 Write `tests/test_diarizer_sidecar.py` FIRST: mock `extract.subprocess.run` +
      `_diarizer_sidecar_python` — sidecar-absent / nonzero-exit / empty-or-bad-JSON / timeout /
      spawn-OSError all → `None`; happy path → parsed turns; out-file cleaned up; child env forces
      CPU + merges parent; timeout override + floor.
- [x] 2.2 Rewrite `extract._run_diarization` to the subprocess seam; add `_diarizer_sidecar_python`
      (override `KB_MCP_DIARIZE_SIDECAR_PYTHON`), `_diarizer_worker_script`, `_diarizer_timeout`
      (duration-scaled, `KB_MCP_DIARIZE_TIMEOUT`). Merge env with `CUDA_VISIBLE_DEVICES=""` +
      `HF_HUB_DISABLE_PROGRESS_BARS=1`. Out-file result channel. Soft-fail on everything.
- [x] 2.3 Delete the dead in-process pipeline symbols `_load_diarization_pipeline` /
      `_get_diarization_pipeline` / `_DIARIZATION_PIPELINE` / `_DIARIZATION_LOCK` (the only main-venv
      `import pyannote.audio`).
- [x] 2.4 Fix the one stale test (`tests/test_extract.py` soft-fail case) to target the new seam
      (`_diarizer_sidecar_python` → None). The `_run_diarization`-mocking tests need no change.

## 3. Deps + provisioning + docs
- [x] 3.1 Remove `pyannote.audio` from the main `pyproject.toml` `diarization` extra (keep
      `speechbrain`); rewrite the torchcodec warning comment (the uninstall dance is retired).
- [x] 3.2 `uv lock` the main project → pyannote 4.0.5 + its tree (incl. torchcodec 0.14.0) dropped.
- [x] 3.3 Add `scripts/setup-diarizer.ps1` (`uv sync --directory`, import smoke, `-Prewarm`); update
      the README env table (`KB_MCP_DIARIZE_SIDECAR_PYTHON`, `KB_MCP_DIARIZE_TIMEOUT`,
      `KB_MCP_DIARIZE_MODEL`) + a "Speaker diarization sidecar" provisioning section.
- [x] 3.4 Add the gated `tests/test_diarizer_worker_smoke.py` (skips unless the sidecar venv exists;
      with a token → happy path, without → graceful nonzero exit).

## 4. Verify
- [x] 4.1 Full suite green via `uv run --no-sync pytest -q` — 824 passed (no regression).
- [x] 4.2 `ruff check` clean on the changed files.
- [x] 4.3 Gated worker smoke passes on the dev box (sidecar built, no token → graceful-failure
      branch verified).
- [ ] 4.4 Deploy-box end-to-end (Hugo runs — needs the sidecar venv + `HUGGINGFACE_TOKEN` + accepted
      gates): `setup-diarizer.ps1 -Prewarm` → `KB_MCP_DIARIZE=1` → restart → diarize a real
      2-speaker recording → confirm `[Hugo]: …` + `[Speaker B]: …` render (sidecar turns flow through
      the unchanged ECAPA naming). Then confirm the embedding stack is intact (a `find` + a fresh
      image/PDF upload still index — no torchcodec/cuDNN regression).
- [x] 4.5 `openspec validate diarization-cpu-sidecar --strict` passes.
