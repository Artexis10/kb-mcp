"""Soft-fail + happy-path contract for the diarization sidecar subprocess boundary.

These are hermetic: they mock the subprocess boundary (`extract.subprocess.run`) and the sidecar
interpreter locator, so no real sidecar venv / pyannote / GPU is needed. The real end-to-end worker
run lives in `test_diarizer_worker_smoke.py` (gated on the sidecar venv being present).

The contract under test: `extract._run_diarization` returns `None` on EVERY failure mode (sidecar
absent, spawn error, nonzero exit, timeout, unparseable output) so `_transcribe` falls back to the
plain transcript and never raises.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from kb_mcp import extract


def _fake_python(monkeypatch) -> None:
    """Make the sidecar locator return a real file so `_run_diarization` proceeds to spawn, and
    short-circuit the PyAV duration probe via the timeout override (keeps the test hermetic)."""
    monkeypatch.setattr(extract, "_diarizer_sidecar_python", lambda: Path(sys.executable))
    monkeypatch.setenv("KB_MCP_DIARIZE_TIMEOUT", "30")


def test_sidecar_absent_returns_none_without_spawning(monkeypatch) -> None:
    monkeypatch.setattr(extract, "_diarizer_sidecar_python", lambda: None)

    def _boom(*a, **k):
        raise AssertionError("subprocess.run must not be called when the sidecar is absent")

    monkeypatch.setattr(extract.subprocess, "run", _boom)
    assert extract._run_diarization(Path("x.wav")) is None


def test_nonzero_exit_returns_none(monkeypatch) -> None:
    _fake_python(monkeypatch)
    monkeypatch.setattr(
        extract.subprocess,
        "run",
        lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom\nmore"),
    )
    assert extract._run_diarization(Path("x.wav")) is None


def test_empty_outfile_returns_none(monkeypatch) -> None:
    # returncode 0 but the worker wrote nothing → the (mkstemp-created, empty) out-file is not
    # valid JSON → soft-fail.
    _fake_python(monkeypatch)
    monkeypatch.setattr(
        extract.subprocess,
        "run",
        lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )
    assert extract._run_diarization(Path("x.wav")) is None


def test_bad_json_returns_none(monkeypatch) -> None:
    _fake_python(monkeypatch)

    def _run(cmd, *a, **k):
        Path(cmd[3]).write_text("not json", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(extract.subprocess, "run", _run)
    assert extract._run_diarization(Path("x.wav")) is None


def test_timeout_returns_none(monkeypatch) -> None:
    _fake_python(monkeypatch)

    def _run(cmd, *a, **k):
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(extract.subprocess, "run", _run)
    assert extract._run_diarization(Path("x.wav")) is None


def test_spawn_oserror_returns_none(monkeypatch) -> None:
    _fake_python(monkeypatch)

    def _run(cmd, *a, **k):
        raise OSError("exec format error")

    monkeypatch.setattr(extract.subprocess, "run", _run)
    assert extract._run_diarization(Path("x.wav")) is None


def test_happy_path_parses_turns(monkeypatch) -> None:
    _fake_python(monkeypatch)

    def _run(cmd, *a, **k):
        Path(cmd[3]).write_text(
            json.dumps(
                {
                    "turns": [
                        {"start": 0.0, "end": 1.5, "label": "SPEAKER_00"},
                        {"start": 1.5, "end": 2.0, "label": "SPEAKER_01"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(extract.subprocess, "run", _run)
    turns = extract._run_diarization(Path("x.wav"))
    assert turns == [(0.0, 1.5, "SPEAKER_00"), (1.5, 2.0, "SPEAKER_01")]


def test_outfile_cleaned_up_after_run(monkeypatch) -> None:
    _fake_python(monkeypatch)
    captured: dict[str, str] = {}

    def _run(cmd, *a, **k):
        captured["out"] = cmd[3]
        Path(cmd[3]).write_text(json.dumps({"turns": []}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(extract.subprocess, "run", _run)
    extract._run_diarization(Path("x.wav"))
    assert not Path(captured["out"]).exists()  # temp out-file removed in the finally block


def test_child_env_forces_cpu_and_merges_parent(monkeypatch) -> None:
    _fake_python(monkeypatch)
    captured: dict[str, dict] = {}

    def _run(cmd, *a, **k):
        captured["env"] = k.get("env") or {}
        Path(cmd[3]).write_text(json.dumps({"turns": []}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(extract.subprocess, "run", _run)
    extract._run_diarization(Path("x.wav"))
    env = captured["env"]
    assert env["CUDA_VISIBLE_DEVICES"] == ""  # sidecar forced to CPU, neutralizes inherited PATH
    assert env.get("HF_HUB_DISABLE_PROGRESS_BARS") == "1"
    # Merged with os.environ (Windows child needs SystemRoot/PATH), not a bare replacement.
    assert any(k.upper() == "PATH" for k in env)


def test_sidecar_python_override_missing_returns_none(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KB_MCP_DIARIZE_SIDECAR_PYTHON", str(tmp_path / "nope.exe"))
    assert extract._diarizer_sidecar_python() is None


def test_timeout_override_and_floor(monkeypatch) -> None:
    monkeypatch.setenv("KB_MCP_DIARIZE_TIMEOUT", "123")
    assert extract._diarizer_timeout(Path("x.wav")) == 123.0
    monkeypatch.delenv("KB_MCP_DIARIZE_TIMEOUT", raising=False)
    # Unprobeable path → the generous floor.
    assert extract._diarizer_timeout(Path("does-not-exist.wav")) >= 900.0
