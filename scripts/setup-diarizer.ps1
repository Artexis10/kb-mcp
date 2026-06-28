# Build the isolated CPU-torch speaker-diarization sidecar venv (sidecar/diarizer/.venv).
#
# Run ONCE per box at deploy time. Requires `uv` on PATH (same as the main `uv sync`); uv
# auto-fetches a compatible Python 3.12 for the sidecar (its pinned torch 2.2.x line has no 3.13
# wheels). NOT needed at service runtime — the running service only invokes the sidecar's
# python.exe by path (extract._diarizer_sidecar_python). pyannote runs here, isolated, because it
# is fundamentally incompatible with the main venv's torch-2.12+cu132 build.
#
# Usage:
#   pwsh -File scripts/setup-diarizer.ps1            # build the venv
#   pwsh -File scripts/setup-diarizer.ps1 -Prewarm   # also download the gated pyannote weights now
#
# After this: set HUGGINGFACE_TOKEN (+ accept conditions for pyannote/speaker-diarization-3.1 and
# pyannote/segmentation-3.0 on huggingface.co), set KB_MCP_DIARIZE=1, and restart the service.
param([switch]$Prewarm)

$ErrorActionPreference = "Stop"

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$DiarizeDir = Join-Path $RepoRoot "sidecar\diarizer"

Write-Host "Building diarizer sidecar venv in $DiarizeDir ..."
uv sync --directory $DiarizeDir   # creates sidecar/diarizer/.venv from pyproject.toml + uv.lock

$Py = Join-Path $DiarizeDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "sidecar venv build failed: $Py missing" }

# Import smoke: proves the pinned stack (pyannote 3.1 / torch 2.2 / torchaudio 2.2 / speechbrain
# 0.5.16 / huggingface_hub 0.25) assembles — i.e. none of the cu132-era version walls are present.
& $Py -c "import warnings; warnings.filterwarnings('ignore'); import torch, torchaudio; from torchaudio import AudioMetaData, list_audio_backends; from pyannote.audio import Pipeline; from faster_whisper.audio import decode_audio; print('diarizer sidecar OK | torch', torch.__version__, '| torchaudio', torchaudio.__version__)"

if ($Prewarm) {
    # Pull the gated pyannote weights into the shared HF cache now, instead of on the first upload.
    # Needs HUGGINGFACE_TOKEN in the environment + accepted model conditions.
    if (-not ($env:HUGGINGFACE_TOKEN -or $env:HF_TOKEN)) {
        Write-Warning "HUGGINGFACE_TOKEN/HF_TOKEN not set - skipping prewarm (gated download would fail)."
    } else {
        Write-Host "Prewarming pyannote weights (downloads to the shared HF cache)..."
        & $Py -c "import os; from pyannote.audio import Pipeline; Pipeline.from_pretrained(os.environ.get('KB_MCP_DIARIZE_MODEL','pyannote/speaker-diarization-3.1'), use_auth_token=os.environ.get('HUGGINGFACE_TOKEN') or os.environ.get('HF_TOKEN'))"
        Write-Host "  weights cached."
    }
}

Write-Host "Done. Sidecar python: $Py"
Write-Host "Next: set HUGGINGFACE_TOKEN, KB_MCP_DIARIZE=1, enroll a speaker, then restart.ps1."
