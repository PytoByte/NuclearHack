#!/bin/sh
# Source from repository root. Uses isolated project SDK/AVD/adb state.
export JAVA_HOME="$PWD/.tools/jdk"
export ANDROID_HOME="$PWD/.tools/android-sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export ANDROID_USER_HOME="$PWD/.tools/android-user"
export ANDROID_AVD_HOME="$PWD/.tools/android-avd"
export ANDROID_ADB_SERVER_PORT=5039
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/19.0/bin:$PWD/.venv/bin:$PWD/.tools/bin:$PATH"
