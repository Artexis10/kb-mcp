#!/usr/bin/env python
"""kb-mcp diarization sidecar — standalone, runs in the isolated CPU-torch sidecar venv.

Reads an audio/video path + an output-file path, decodes to 16 kHz mono, runs the pyannote
speaker-diarization pipeline, and writes ``{"turns":[{"start","end","label"}, ...]}`` as UTF-8
JSON to the output file. Any failure → a message on stderr + a nonzero exit; the caller (the main
cu132 venv, in ``extract._run_diarization``) maps that to ``None`` → plain transcript. This file
MUST NOT import ``kb_mcp`` — it runs under a *different* interpreter/venv.

Why a separate venv: the main service runs a custom torch-2.12+cu132 (Blackwell) build that is
fundamentally incompatible with the pyannote/torchaudio audio-ML ecosystem (torchcodec native-lib
load failure, removed torchaudio APIs, speechbrain LazyModule). pyannote is rock-solid on standard
CPU torch, so it lives here behind a subprocess boundary while the main service keeps cu132 for
whisper/CLIP/bge.

The result channel is the OUT-FILE (plus the exit code), never stdout: pyannote / pytorch-lightning
/ tqdm / huggingface_hub can print to stdout during model load, which would corrupt a JSON-on-stdout
contract. ``main`` redirects stdout to stderr before doing anything heavy.
"""
from __future__ import annotations

import json
import os
import sys

# Quiet HF download bars / warnings before the heavy imports so they take effect during model load.
# (The parent also sets these in the child env; setdefault makes the worker robust when run directly.)
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("PYTHONWARNINGS", "ignore")


def _decode(path: str):
    """Decode any audio/video to a ``(1, N)`` float32 16 kHz mono torch tensor via faster-whisper's
    PyAV path — the SAME decoder the main ASR uses, so turns share the whisper timebase."""
    import torch
    from faster_whisper.audio import decode_audio

    samples = decode_audio(path, sampling_rate=16000)
    return torch.as_tensor(samples, dtype=torch.float32).unsqueeze(0)


def _load_pipeline():
    """Load the pretrained pyannote diarization pipeline (model + HF token from env)."""
    from pyannote.audio import Pipeline

    model = os.environ.get("KB_MCP_DIARIZE_MODEL", "pyannote/speaker-diarization-3.1")
    token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    # pyannote 4.x renamed the HF-auth kwarg `use_auth_token` → `token`; support both so the same
    # worker loads under either (this venv pins <4, but the fallback is cheap insurance).
    try:
        return Pipeline.from_pretrained(model, token=token)
    except TypeError:
        return Pipeline.from_pretrained(model, use_auth_token=token)


def _diarize(audio_path: str) -> list[dict]:
    waveform = _decode(audio_path)
    pipeline = _load_pipeline()
    if pipeline is None:
        # pyannote returns None (rather than raising) when it can't load a gated checkpoint —
        # almost always a missing/invalid HF token or un-accepted model conditions. Make that
        # explicit so the caller's stderr log is actionable instead of "NoneType not callable".
        raise RuntimeError(
            "pyannote pipeline failed to load — gated model needs a valid HUGGINGFACE_TOKEN "
            "and accepted conditions for speaker-diarization-3.1 + segmentation-3.0"
        )
    annotation = pipeline({"waveform": waveform, "sample_rate": 16000})
    return [
        {"start": float(turn.start), "end": float(turn.end), "label": str(label)}
        for turn, _track, label in annotation.itertracks(yield_label=True)
    ]


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: worker.py <audio_path> <out_json_path>", file=sys.stderr)
        return 2
    audio_path, out_path = argv[1], argv[2]
    # Redirect stdout → stderr so any pyannote/lightning/tqdm print can't corrupt the result.
    sys.stdout = sys.stderr
    turns = _diarize(audio_path)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"turns": turns}, fh)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — any failure → nonzero exit + stderr; caller soft-fails
        print(f"diarizer worker failed: {type(e).__name__}: {e}", file=sys.stderr)
        raise SystemExit(1) from e
