# Goals and Task Alignment

This file is the short planning/matrix view. Technical truth is in
`ARCHITECTURE.md`; research history and measurement provenance are in
`RESEARCH.md`. Do not duplicate baseline implementation details here.

## Feature statuses

Current core baseline is implemented; detailed requirements are omitted to
avoid duplicating `AGENTS.md`/`task/task.md`.

| Goal | Status | Notes |
| --- | --- | --- |
| In-app audio recording | Planned | Task permits import or app recording. App currently imports audio through SAF. |
| Real-time transcription mode | Optional | Android setting is disabled; SDK is buffered file processing. Do not call the current SDK real-time ASR. |
| Local LLM audit/summary | Planned | Optional Qwen path exists. Transcript JSON is not replaced, only summarized separately. |
| Evaluator model delivery guidance | Required docs | Exact presets, scripts, model sets, and hashes must remain documented. |
| Measurement provenance | Required docs | Every claim must be labeled host / AVD4096MiB / physical ARM. |
| Android full benchmark | Not measured | Full app benchmark must not be implied. Native or host numbers are not Android evidence. |
| ARM physical device metrics | Optional / Unmeasured | Cross-build exists; physical ARM runtime and quality are not measured. |

## Non-targets

- Cross-session / cross-file speaker identity.
- Channel-aware diarization.
- Realtime microphone ASR as default product behavior.
- Forced alignment / manual word timestamps unless new ground truth is collected.

## Metric rules

- Label every metric with run ID and platform.
- Use `not measured` when no artifact exists.
- Host screening metrics are not final Android metrics.
- Word timestamp accuracy cannot be claimed without manual word-level ground truth.
```

Then edit AGENTS. Let's do.