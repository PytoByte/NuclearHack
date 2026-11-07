#!/bin/sh
set -e
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT/src/audio"

echo "pre-push: генерация compile_commands.json..."
cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

echo "pre-push: clang-tidy..."
run-clang-tidy -p build -j"$(nproc)" 2>&1 | tee clang-tidy.log

echo "pre-push: cppcheck..."
"$ROOT/scripts/cppcheck.sh"

echo "pre-push: OK"