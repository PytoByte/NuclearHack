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
- Evaluate text, speakers, timing, punctuation and resources together. The user
  reports substantial scoring across components; do not optimize only WER/RTF
  or invent a new numerical score without an agreed evaluation protocol.

## Outstanding quality goals

- Reproduce music/rap failures when the recordings are available, record source
  hashes and annotation provenance, and define what counts as each speaker.
- Trace incorrect words through backend ASR text, word assembly and final JSON;
  separate acoustic/decoding errors from boundaries/merge and attribution errors.
- Test causal block changes for musical accompaniment, short/overlapping voices
  and chunk boundaries. Check gains against ordinary Russian dialogue controls.
- Keep separate per-domain reports and a Pareto/tradeoff view of WER/CER,
  punctuation, DER/JER/cpWER, timestamps when annotated, and RTF/RAM.
- Investigate the "Серёга Пират" speaker case; do not assign unrelated historical
  metrics to it without a matching source/run.
- Add independent dialogue data/word timing references where feasible. Existing
  known silver files are regression controls, not a fresh blind test.

## Client and delivery follow-up

- Continue timer/live-stage/diagnostics work and show the build/version identity.
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
  ARM performance from cross-build, or synthetic soak as natural-dialogue quality.

## Metric rules

Every number names its run ID, corpus/protocol and platform. Missing measurements
stay `null`/`not measured` with a reason. User observations, host screening,
AVD4096MiB SDK runs and full-app measurements remain distinct evidence.
