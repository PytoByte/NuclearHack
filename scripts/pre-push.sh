#!/bin/sh
set -e
cd "$(git rev-parse --show-toplevel)/src/mobile/android"
echo "pre-push: Android Lint..."
./gradlew --daemon :app:lintDebug
echo "pre-push: OK"
