# AGENTS.md

## Read-only directory rule

- `task/` contains the competition brief and reference materials.
- Treat `task/` as **read-only**.
- Do **not** create, edit, delete, rename, move, or overwrite any file under `task/` (including nested files).
- Only read files from `task/` for requirements and context.
- If a requested change targets `task/`, refuse it and make the change elsewhere in the repository instead.
- When unsure whether a path is inside `task/`, check the path before writing.

## Audio development workflow

- Read `docs/ARCHITECTURE.md` and `docs/RESEARCH.md` before audio work.
  `docs/AGENT_AUDIO_HACKATHON.md` is the user's preserved planning reference;
  the current headless SDK scope overrides its Android-app-first sequence.
- Work on `dev`; preserve unrelated user changes. Native SDK: C++17/C ABI.
- Keep `docs/ARCHITECTURE.md` aligned with implemented/accepted code. Record
  stages, concise experiments and ADRs in `docs/RESEARCH.md`; avoid extra docs.
- Run `make check`, `make native-test`, `make native-sanitize` for native changes;
  `make mobile-build` checks ABI only, not Android execution or RAM.
- Validate transcript exports and pinned model files with `scripts/audio_tools.py`.
- Keep unique experiment IDs/configs/raw logs. Distinguish host and Android
  metrics; never invent missing measurements or treat read speech as dialogues.
- Keep audio, model weights and raw logs out of Git. Downloads run only on the
  developer machine; user-audio processing in the shipped SDK stays offline.

## Качество кода

- Установить Git-хуки: `./gradlew installGitHooks`
- Локальный прогон ktlint и detekt: `./gradlew ktlintCheck detekt`
- Локальный прогон Android Lint: `./gradlew :app:lintDebug`
- Перед коммитом хуки запускаются автоматически; не используй `--no-verify`.
