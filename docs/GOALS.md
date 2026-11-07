# Goals and Task Alignment

Short planning and goal view. Technical truth is in `ARCHITECTURE.md`;
research history and measurement provenance are in `RESEARCH.md`. Keep this
file focused on outstanding goals and non-targets.

## Outstanding goals

### Processing UX

- Implemented: visible elapsed timer while transcription is running.
- Implemented: live "what is happening now" indicator based on native SDK
  progress stages.
- Implemented: on-demand detailed diagnostics/logs dialog.
- Implemented: clear progress health state showing whether processing is
  progressing, waiting, or has no updates.
- Implemented: percentage is displayed as part of the live stage state only.
- Implemented: audible/visual processing-state label exposed semantically on
  the processing card.

### App build clarity

- Display build/version label in the app.
- Make it obvious whether the APK is an old or current build.
- Link build label to Git commit/build provenance where practical.

### Quality and documentation

- Add evaluator model delivery guidance: exact presets, scripts, model sets,
  and hashes.
- Label every metric as host, AVD4096MiB, or physical ARM.
- Run Android app benchmarks where feasible, with run IDs.
- Investigate and improve quality on the "Серёга Пират" speaker case.

## Optional goals

- Real-time transcription mode: Android setting stays disabled until the core
  buffered SDK gains an explicit streaming profile.
- Local LLM audit or summary: planned as a separate optional path; transcript
  JSON is never replaced.
- In-app audio recording: planned. Import through SAF already works.

## Non-targets

- Cross-session / cross-file speaker identity.
- Channel-aware diarization.
- Realtime microphone ASR as default product behavior.
- Forced alignment or manual word timestamps unless new ground truth exists.
- Full Android app performance claim when no measured artifact exists.
- Physical ARM quality claim from cross-compile alone.

## Metric rules

- Label each metric with run ID and platform.
- Use `not measured` when no artifact exists.
- Host screening metrics are not final Android evidence.
- Word timestamp accuracy cannot be claimed without manual word-level ground
  truth.