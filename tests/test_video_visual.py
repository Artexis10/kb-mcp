"""Video visual search — no-audio handling + CLIP keyframe embedding (engines stubbed)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from kb_mcp import backfill, embeddings, extract, media_worker, preserve


def test_transcribe_silent_video_is_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # A video with no audio stream → empty transcript, engine "no-audio", never raises,
    # and Whisper is never even loaded.
    monkeypatch.setattr(extract, "_has_audio_stream", lambda p: False)
    monkeypatch.setattr(extract, "_get_whisper", lambda: (_ for _ in ()).throw(AssertionError("loaded whisper")))
    r = extract._transcribe(Path("clip.mp4"), "video")
    assert r.text == "" and r.engine == "no-audio" and r.media_type == "video"


def _three_frames():
    """Stub embed_video_frames output: three keyframes at distinct timestamps."""
    return [
        (5.0, np.eye(1, embeddings.CLIP_DIM, 0, dtype=np.float32)[0]),
        (15.0, np.eye(1, embeddings.CLIP_DIM, 1, dtype=np.float32)[0]),
        (25.0, np.eye(1, embeddings.CLIP_DIM, 2, dtype=np.float32)[0]),
    ]


def test_worker_clip_embeds_video_via_keyframes(vault, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KB_MCP_DISABLE_CLIP", raising=False)
    monkeypatch.delenv("KB_MCP_DISABLE_MEDIA_EXTRACTION", raising=False)
    res = preserve.preserve_bytes(
        vault, scope="Yolo", category="clips", filename="demo.mp4", data=b"\x00\x00video", text="x",
    )
    called = {}
    monkeypatch.setattr(embeddings, "embed_video_frames", lambda p: called.setdefault("v", _three_frames()))
    monkeypatch.setattr(embeddings, "embed_image", lambda p: (_ for _ in ()).throw(AssertionError("used embed_image for video")))
    w = media_worker.MediaWorker(vault)
    w._process(media_worker._Job(
        binary_path=vault / res.path, sidecar_path=vault / res.sidecar_path,
        media_type="video", do_ocr=False, do_clip=True,
    ))
    assert "v" in called  # per-keyframe path was used, not embed_image
    idx = embeddings.ClipIndex(vault)
    assert idx.has(res.path)
    paths, _, _ = idx.all_vectors()
    assert paths.count(res.path) == 3  # one row per keyframe, not one mean-pool


def test_backfill_clip_indexes_video(vault, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KB_MCP_DISABLE_CLIP", raising=False)
    p = vault / "Knowledge Base/Evidence/Old/clips/legacy.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x00video")
    monkeypatch.setattr(embeddings, "embed_video_frames", lambda f: _three_frames())
    stats = backfill.backfill_media(vault, do_ocr=False, log_fn=lambda *a: None)
    assert stats.clip_indexed == 1
    rel = "Knowledge Base/Evidence/Old/clips/legacy.mp4"
    idx = embeddings.ClipIndex(vault)
    assert idx.has(rel)
    paths, _, _ = idx.all_vectors()
    assert paths.count(rel) == 3
