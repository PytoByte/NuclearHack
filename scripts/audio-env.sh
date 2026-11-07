#!/bin/sh
# Source from the repository root: . scripts/audio-env.sh
export PATH="$PWD/.venv/bin:$PWD/.tools/bin:$PATH"
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-4}"
