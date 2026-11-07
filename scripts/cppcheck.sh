#!/bin/sh
set -e
cd "$(git rev-parse --show-toplevel)/src/audio"
cppcheck --enable=warning,style,performance \
  --language=c++ --std=c++20 \
  --inline-suppr \
  --error-exitcode=1 \
  --suppress=missingIncludeSystem \
  -I include/ src/