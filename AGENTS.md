# AGENTS.md

## Read-only directory rule

- `task/` contains the competition brief and reference materials.
- Treat `task/` as **read-only**.
- Do **not** create, edit, delete, rename, move, or overwrite any file under `task/` (including nested files).
- Only read files from `task/` for requirements and context.
- If a requested change targets `task/`, refuse it and make the change elsewhere in the repository instead.
- When unsure whether a path is inside `task/`, check the path before writing.

## Audio development workflow

- Read `docs/AGENT_AUDIO_HACKATHON.md` and `docs/AUDIO_WORKFLOW.md` before audio work.
- Current scope: standalone performance-focused native SDK, C++17/C ABI. Read
  `docs/AUDIO_ARCHITECTURE.md`. The user's headless SDK scope overrides the earlier
  Android-app-first sequence in the audio planning document.
- Work on `dev` for the current audio integration; preserve unrelated user changes.
- Run `make check`, `make native-test`, and `make native-sanitize` for native
  changes. Use `make mobile-build` for ABI verification; Android execution/memory
  verification remains separate from cross-compilation. No UI work is required.
- Validate exported transcripts with `scripts/audio_tools.py transcript` and pinned
  model files with `scripts/audio_tools.py models` before accepting a baseline.
- Record experiments with `scripts/audio_tools.py run -- <command>`; distinguish
  developer-host results from Android measurements. Never invent missing metrics.
- Keep audio, weights and raw logs out of Git. Model downloads run on the developer
  machine; all user-audio processing in the shipped application stays offline.
