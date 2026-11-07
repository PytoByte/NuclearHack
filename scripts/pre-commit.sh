#!/bin/sh
set -e
cd "$(git rev-parse --show-toplevel)/src/mobile/android"
echo "pre-commit: ktlint + detekt..."
./gradlew --daemon ktlintCheck detekt
echo "pre-commit: OK"
