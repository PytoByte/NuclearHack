# AGENTS.md

## Read-only `task/`

- `task/` is **read-only**: contains the competition brief and reference materials.
- Do **not** create, edit, delete, rename, move, or overwrite anything under
  `task/` (including nested files). Only read it for requirements and context.
- If a requested change targets `task/`, refuse it and make the change elsewhere.
- When unsure whether a path is inside `task/`, check the path before writing.

## Common workflow

- Create a separate branch from the current base branch (`dev`) for the task;
  preserve unrelated user changes.
- Read `docs/ARCHITECTURE.md`, `docs/GOALS.md`, `docs/RESEARCH.md` before
  audio work.
- `task/task.md` is the original competition brief and Android-app-first
  reference; the current headless SDK scope overrides that sequence.
- Native SDK: C++17 / C ABI.
- Run focused tests during iterations; run full gates at task end, not every
  iteration.
- Never use `--no-verify`. Configure hooks once:
  - `cd src/mobile/android && ./gradlew installGitHooks`
  - `pre-commit install -f` at repo root (replaces the legacy migration hook).
- Preserve pre-existing formatting in native files; let pre-commit clang-format
  adjust staged code. Do not stage generated logs, `.build`, models, or weights.
- Keep audio, model weights, and raw logs out of Git. Downloads run only on the
  developer machine; user-audio processing in the shipped SDK stays offline.
- Keep unique experiment IDs/configs/raw logs. Never invent missing measurements
  or treat read speech as dialogues.

## Documentation

- `docs/ARCHITECTURE.md`: keep aligned with implemented/accepted code.
- `docs/RESEARCH.md`: record stages, concise experiments, and ADRs. Avoid extra docs.
- Update related docs in the same change when behavior, API, config, build command,
  model availability, or public limitations change.
  - `src/audio` API/config -> `docs/ARCHITECTURE.md`, `docs/GOALS.md`
  - rules/process -> `AGENTS.md`
  - optional/unimplemented items -> `docs/GOALS.md`

## Native audio (`src/audio`)

- C++17 / C ABI, clang-format, focused tests during iteration, full native gates
  before commit.
- For native changes run `make check`, `make native-test`, `make native-sanitize`.
- `make mobile-build` checks ABI only — not Android execution or RAM.
- Validate transcript exports and pinned model files with `scripts/audio_tools.py`.

## Android (`src/mobile/android`)

- Client only: Kotlin/Compose MVVM + JNI bridge. Gradle consumes synced native
  libraries and local models; it does not build the native SDK.
- Build order: `make mobile-build` -> `make android-app` (after model bootstrap).
- Required env: `JAVA_HOME` and `ANDROID_HOME` under `.tools`.
- Keep `android.builder.sdkDownload=false` to avoid platform-tools download
  hanging; the warning is acceptable.
- Offline invariant: `INTERNET` must stay absent from the manifest. Models remain
  assets copied to `filesDir/models`. Shipped SDK/app have no network access.
  Models are bootstrapped by developer tooling only.
- Presets: final preset first, legacy preset as fallback. Optional Qwen summary
  only when runtime and weights are present; it does not change transcript JSON.
- Keep blocking native calls on the IO dispatcher.
- Quality tools (run before finalizing, not every iteration):
  - `cd src/mobile/android && ./gradlew ktlintCheck detekt`
  - `cd src/mobile/android && ./gradlew :app:lintDebug`
- Build gates do not replace focused tests; full gates run before commit.
- See `src/mobile/android/README.md` for manual build and bootstrap details.

## Metrics provenance

- Every metric must name its run ID and platform.
- Full Android app benchmarks are not claimed unless measured. Host numbers are
  not Android evidence — label as `host`, `AVD4096MiB`, or `physical ARM`.