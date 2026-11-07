# Goals and Task Alignment

Short planning and goal view. Technical truth is in `ARCHITECTURE.md`;
research history and measurement provenance are in `RESEARCH.md`. Keep this
file focused on outstanding goals and non-targets.

## Outstanding goals

### Processing UX

- Add a visible elapsed timer while transcription is running.
- Add a live "what is happening now" indicator using native SDK progress
  stages.
- Add on-demand detailed logs or diagnostics for debug and user explanation.
- Make clear whether processing is frozen or progressing.
- Show percentage long enough only as part of the live stage state, not as
  ambiguous frozen progress.
- Add an audible/visual processing-state label on the transcript card.

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