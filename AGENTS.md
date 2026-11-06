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
- Work on `dev` for the current audio integration; preserve unrelated user changes.
- Run `make check` and `make test` for automation changes; run `make android-check`
  for Android integration when the documented environment is available.
- Validate exported transcripts with `scripts/audio_tools.py transcript` and pinned
  model files with `scripts/audio_tools.py models` before accepting a baseline.
- Record experiments with `scripts/audio_tools.py run -- <command>`; distinguish
  developer-host results from Android measurements. Never invent missing metrics.
- Keep audio, weights and raw logs out of Git. Model downloads run on the developer
  machine; all user-audio processing in the shipped application stays offline.
