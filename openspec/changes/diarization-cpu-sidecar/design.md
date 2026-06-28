# Design — Diarization CPU-torch sidecar

## Context

`extract._diarize` runs pyannote `speaker-diarization-3.1` → `[(start,end,raw_label)]` →
ECAPA named attribution → `[Speaker A]:` / `[Hugo]:` turns, gated by `KB_MCP_DIARIZE`,
soft-fail to plain transcript. The named-attribution layer works on the main cu132 venv; the
pyannote pipeline does not load there at all. Six version walls were diagnosed and confirmed
un-patchable on cu132 (torchcodec, torchaudio API removals, speechbrain LazyModule, hf_hub
`use_auth_token` removal, the `token` kwarg rename). The root cause is that the custom
`torch-2.12+cu132` pin transitively forces `torchaudio 2.11` + `pyannote 3.4` + `speechbrain 1.x`
+ `huggingface_hub` 1.x — the exact broken combo. They are version walls, so CPU torch alone
does not help; the fix is the *freedom to choose versions*, which an isolated venv gives.

## The seam

`_run_diarization(path) -> list[(start,end,label)] | None` is the **only** function that touches
pyannote. Downstream (`_resolve_named_labels` → `voice_embed.embed_spans` → `speaker_attribution`
→ `_diarize`) consumes the turns list and is untouched. So the entire change is: swap that one
function's body for a subprocess call, and provide the sidecar that answers it.

**IPC contract:** audio file *path* in (argv) → JSON `{"turns":[{"start","end","label"}]}` in an
*out-file* (argv) out. **Soft-fail contract (preserved byte-for-byte):** `_run_diarization`
returns `None` on any failure → `_diarize` returns `None` → `_transcribe` emits the plain
transcript. Never raises.

## Decisions

- **Isolated uv project with a deliberately-OLD pinned stack.** `sidecar/diarizer/pyproject.toml`
  pins `pyannote.audio 3.1.1` / `torch 2.2.2+cpu` / `torchaudio 2.2.2+cpu` / `speechbrain 0.5.16`
  / `huggingface_hub 0.25` (Python 3.12, auto-fetched by uv). Each pin clears a specific wall:
  torchaudio 2.2 still has `AudioMetaData` + `list_audio_backends`; speechbrain 0.5.x has no
  LazyModule; hf_hub 0.25 still has `use_auth_token`; no torchcodec is pulled. **These pins are
  load-bearing — `uv lock --upgrade` would float back into the trap.** Empirically validated on the
  Windows box: the full stack imports and the worker runs end-to-end up to the gated model.
- **Sidecar decodes via faster-whisper `decode_audio`** (the same decoder the main ASR uses) and
  feeds pyannote a pre-decoded `{waveform, sample_rate}` dict — guarantees timebase parity with
  the whisper segments the main venv assigns turns to, and avoids torchaudio/torchcodec decode.
- **Out-file result channel, not stdout.** pyannote/lightning/tqdm/hf print to stdout during model
  load; the worker redirects stdout→stderr and writes JSON to the out-file. The success signal is
  the exit code + a parseable out-file, never stdout content.
- **Spawn-per-file (MVP).** The media worker is single-threaded, so there's never more than one
  diarizer subprocess; uploads are occasional and diarization runs off the request path. The
  ~seconds of per-call model load is noise next to whisper ASR on the same file, and spawn-per-file
  gives crash isolation for free. A long-lived worker (amortized load, but health/restart/hang
  plumbing) is a future option, not the MVP.
- **Child env: merge + force CPU.** `env={**os.environ, "CUDA_VISIBLE_DEVICES": "",
  "HF_HUB_DISABLE_PROGRESS_BARS": "1"}` — merge (a Windows child needs SystemRoot/PATH), CUDA off
  forces the sidecar's CPU torch and neutralizes the cu12 PATH poisoning the main process applied
  in `_ensure_cuda_dll_path`. The HF token + `KB_MCP_DIARIZE_MODEL` flow through via inheritance.
- **Duration-scaled timeout.** `max(900, duration×6)` seconds, `KB_MCP_DIARIZE_TIMEOUT` overrides.
  CPU pyannote is slow and the first call also downloads weights; a hung child blocks the single
  media thread, so we over-budget rather than kill a valid long job. `TimeoutExpired` → `None`.
- **Locate, never auto-build.** `_diarizer_sidecar_python()` returns the venv interpreter (or the
  `KB_MCP_DIARIZE_SIDECAR_PYTHON` override), or `None` if unbuilt → plain transcript + a clear log.
  Runtime never runs `uv` (avoids the fragile-interpreter hazard `restart.ps1` already guards).
- **Remove pyannote from the main venv.** Leaving it reachable in cu132 is an active hazard: a
  future `uv sync --extra diarization` re-pulls `torchcodec`, which breaks the embedding stack on
  the next restart. The main `diarization` extra is now `speechbrain`-only.

## Version-decoupling (why sidecar pyannote can't affect naming)

The sidecar returns only opaque anonymous `(start,end,label)` turns. All ECAPA embedding and cosine
matching against enrolled profiles happens main-side on the *original* file
(`voice_embed.embed_spans` re-decodes; `speaker_attribution.attribute_clusters`). A pyannote upgrade
in the sidecar can only change clustering granularity and label strings — both consumed opaquely,
and the average-linkage merge absorbs over/under-splitting. Enrolled-profile matching is not coupled
to the sidecar's pyannote version.

## Risks

- **Sidecar venv drift / disappearance** (Kaspersky quarantine per `restart.ps1`; a bare main
  `uv sync` does not touch the sidecar). The `is_file()` guard degrades to plain transcript;
  recovery is `setup-diarizer.ps1`. Add a Kaspersky exclusion for `sidecar/diarizer/.venv`.
- **Gated weights.** First diarized upload downloads pyannote weights into the shared HF cache;
  `setup-diarizer.ps1 -Prewarm` front-loads it. Needs `HUGGINGFACE_TOKEN` + accepted conditions for
  `speaker-diarization-3.1` and `segmentation-3.0`.
- **Concurrency coupling.** Safety assumes the media worker stays single-threaded; raising worker
  concurrency later would need to bound concurrent diarizer subprocesses (each holds a model + the
  waveform in RAM) and could race the HF cache on first download.
