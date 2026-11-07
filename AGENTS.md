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
  `task/task.md` is the original competition brief and Android-app-first
  reference; the current headless SDK scope overrides that sequence.
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
- Android client integration: use `make android-app` after `mobile-build` and
  model bootstrap. Do not run quality gates on every iteration; run them at
  task end once working code exists. Required env: `JAVA_HOME` and
  `ANDROID_HOME` under `.tools`; `android.builder.sdkDownload=false` keeps
  platform-tools download from hanging, the warning is acceptable.
- Preserve pre-existing formatting edits in native files; let pre-commit
  clang-format adjust staged code instead of hand-formatting or reformatting
  unrelated files. Do not stage generated logs, `.build`, models or weights.

## Качество кода

- Во время активной разработки не гоняйте полные quality gates (`make check`, `make native-test`, `make native-sanitize`, ktlint/detekt/Lint) на каждую итерацию; они замедляют цикл. Запускайте их в конце задачи, когда код уже работает, но стиль, типизация или регрессии остаются неясными.
- Настроить Git-хуки: `cd src/mobile/android && ./gradlew installGitHooks`; в корне репозитория дополнительно выполнить `pre-commit install -f`, чтобы убрать устаревший migration hook `pre-commit.legacy` с Gradle
- Локальный прогон ktlint и detekt: `cd src/mobile/android && ./gradlew ktlintCheck detekt`
- Локальный прогон Android Lint: `cd src/mobile/android && ./gradlew :app:lintDebug`
- Перед коммитом хуки запускаются автоматически; не используй `--no-verify`.
