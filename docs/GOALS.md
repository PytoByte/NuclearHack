# Goals and Task Alignment

Current priorities, not a completed checklist. Architecture: `ARCHITECTURE.md`.
Research loop and tools: [AUDIO_RESEARCH_AGENT.md](AUDIO_RESEARCH_AGENT.md).
Measured results and ADRs: `RESEARCH.md`.

## Current user decisions — 07.11.2026

- The user verified the application journey and confirmed it works. Do not
  reopen it as a functional blocker. This is user verification, not a new
  instrumented APK quality/time/memory benchmark.
- LLM/summary is outside current scope: it does not serve a transcription block,
  is not wanted as an extra feature, and adds substantial model weight.
- Main work is quality. On personal music/rap files the user reports speaker
  errors and word errors: extra letters or merged words despite intelligible
  sounds/meaning. These are qualitative observations, not measured WER/DER.
- The user has not yet tested ordinary speech. Keep it a separate control slice.
- Observability is being improved in the client.
- Latest priority: stronger ASR/text with punctuation first; diarization, overlap
  and timing remain measured, but do not trade away ASR quality for speaker quality.
  Evaluate all components and RTF/RAM without inventing numerical scoring weights.
- APK size is not graded according to the Q&A. Do not reject larger weights solely
  for distribution size; the4GB AVD memory limit and runtime cost still apply.

## Processing UX

Implemented in the current client:

- visible elapsed timer while transcription is running;
- live "what is happening now" indicator based on native SDK progress stages;
- on-demand detailed diagnostics/logs dialog;
- clear progress health state showing whether processing is progressing,
  waiting, or has no updates;
- percentage displayed as part of the live stage state only;
- audible/visual processing-state label exposed semantically on the processing
  card.

## Outstanding quality goals

- Reproduce music/rap failures when the recordings are available, record source
  hashes and annotation provenance, and define what counts as each speaker.
- Trace incorrect words through backend ASR text, word assembly and final JSON;
  separate acoustic/decoding errors from boundaries/merge and attribution errors.
- Compare stronger ASR/context/decoding candidates against the current model;
  quantization/FP32 is an experimental factor, not an automatic quality ranking.
- Test causal block changes for musical accompaniment, short/overlapping voices
  and chunk boundaries. Check gains against ordinary Russian dialogue controls.
- Report ASR recovery and speaker attribution separately for overlapping speech.
- Keep separate per-domain reports and a Pareto/tradeoff view of WER/CER,
  punctuation, DER/JER/cpWER, timestamps when annotated, and RTF/RAM.
- Investigate the "Серёга Пират" speaker case; do not assign unrelated historical
  metrics to it without a matching source/run.
- Add independent dialogue data/word timing references where feasible. Existing
  known silver files are regression controls, not a fresh blind test.

## Client and delivery follow-up

- Continue timer/live-stage/diagnostics work and show the build/version identity.
- Display build/version label in the app and make it obvious whether the APK is
  an old or current build; link the label to Git commit/build provenance where
  practical.
- Select packaged files from the active preset/lock manifest; avoid copying
  unused Qwen, alternative weights and unrelated legacy models merely because
  they exist on the developer machine.
- Keep evaluator delivery instructions consistent with actual model IDs/hashes.
- Record full-app performance separately when measured. SDK CLI runs do not
  become app benchmarks because the user journey was verified manually.

## Optional and non-target work

- Real-time transcription and in-app recording are separate future tasks;
  buffered file processing is the current mode.
- No new LLM audit/summary feature or required Qwen delivery. Existing optional
  APIs may remain for compatibility; they never rewrite transcript JSON.
- Cross-file speaker identity and channel-aware diarization are not immediate
  product goals. Explore only under an explicit useful quality hypothesis.
- No accuracy claim for word timestamps without manual ground truth, physical
  ARM performance from cross-build, or synthetic soak as natural-dialogue
  quality.

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
- Every number names its run ID, corpus/protocol and platform. Missing
  measurements stay `null`/`not measured` with a reason. User observations,
  host screening, AVD4096MiB SDK runs and full-app measurements remain distinct
  evidence.
