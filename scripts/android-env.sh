#!/bin/sh
# Resolve the repo root relative to this script so the Android SDK/JDK config
# works when sourced from any directory. Prefer BASH_SOURCE for the sourced case;
# fall back to $0 when the script is executed directly.
if [ -n "${BASH_SOURCE:-}" ]; then
  SCRIPT_PATH="${BASH_SOURCE[0]}"
elif [ -n "${0:-}" ] && [ "${0##*/}" != "sh" ] && [ "${0##*/}" != "bash" ]; then
  SCRIPT_PATH="$0"
else
  SCRIPT_PATH="$(command -v "$0" 2>/dev/null || printf '%s' "$0")"
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)

export JAVA_HOME="$REPO_ROOT/.tools/jdk"
export ANDROID_HOME="$REPO_ROOT/.tools/android-sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export ANDROID_USER_HOME="$REPO_ROOT/.tools/android-user"
export ANDROID_AVD_HOME="$REPO_ROOT/.tools/android-avd"
export ANDROID_ADB_SERVER_PORT=5039
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/19.0/bin:$REPO_ROOT/.venv/bin:$REPO_ROOT/.tools/bin:$PATH"
