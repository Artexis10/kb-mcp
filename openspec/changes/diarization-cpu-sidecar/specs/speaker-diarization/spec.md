## ADDED Requirements

### Requirement: Isolated Diarization Execution

The system SHALL run the pyannote who-spoke-when pipeline in an isolated sidecar virtual
environment (standard CPU torch) as a subprocess, and SHALL NOT import pyannote in the main service
process. The main process SHALL pass the audio file path to the sidecar and receive speaker turns
as JSON; it SHALL resolve those anonymous turns to enrolled names via the existing main-process
ECAPA attribution, which is unaffected by the sidecar's pyannote version. Any failure of the
sidecar — its venv not provisioned, a spawn error, a nonzero exit, a timeout, or unparseable
output — SHALL be logged and degrade to the plain transcript (or anonymous diarization), and MUST
NOT raise.

#### Scenario: Diarization runs in the sidecar subprocess

- **WHEN** `KB_MCP_DIARIZE` is set and the diarizer sidecar venv is provisioned
- **THEN** the main process spawns the sidecar interpreter on `worker.py` with the audio path and
  an output-file path
- **AND** the sidecar writes `{"turns": [{"start", "end", "label"}, …]}` JSON to the output file
- **AND** the main process parses it into `[(start, end, raw_label)]` and feeds it to the unchanged
  named-attribution path

#### Scenario: Sidecar not provisioned degrades to plain transcript

- **WHEN** `KB_MCP_DIARIZE` is set but `sidecar/diarizer/.venv` (or `KB_MCP_DIARIZE_SIDECAR_PYTHON`)
  resolves to no interpreter
- **THEN** no subprocess is spawned, the condition is logged, and extraction emits the plain
  transcript
- **AND** the result is byte-identical to diarization being disabled

#### Scenario: Sidecar failure soft-fails

- **WHEN** the sidecar subprocess exits nonzero, times out, or writes no parseable turns
- **THEN** the failure is logged and the file's transcript falls back to plain ASR (no diarization)
- **AND** the transcript and its other extracted fields are persisted unchanged

#### Scenario: Main process never imports pyannote

- **WHEN** the main service venv has pyannote removed (the `diarization` extra installs only
  speechbrain for ECAPA)
- **THEN** diarization still functions via the sidecar
- **AND** the main venv never imports `pyannote.audio`, so the cu132 torchcodec/torchaudio
  incompatibility cannot affect the embedding stack

### Requirement: Diarization Sidecar Provisioning

The diarizer sidecar SHALL be a self-contained, reproducibly-pinned uv project that is provisioned
at deploy time and never built or resolved at service runtime. The sidecar SHALL pin a torch /
torchaudio / pyannote / speechbrain / huggingface_hub combination free of the cu132-era version
walls, independent of the main venv's torch pin. The running service SHALL invoke the sidecar
interpreter only by path.

#### Scenario: Provisioned once per box

- **WHEN** an operator runs `scripts/setup-diarizer.ps1` on a box
- **THEN** the sidecar venv is built from its committed `pyproject.toml` + `uv.lock`
- **AND** the running service needs only the sidecar interpreter path thereafter, never `uv`

#### Scenario: Pinned stack clears the version walls

- **WHEN** the sidecar resolves its dependencies
- **THEN** torchaudio retains `AudioMetaData` / `list_audio_backends`, speechbrain is pre-LazyModule,
  huggingface_hub retains `use_auth_token`, and no torchcodec is pulled
- **AND** the pyannote pipeline imports and loads on a Blackwell/cu132 host outside the main venv
