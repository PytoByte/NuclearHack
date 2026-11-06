#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec .venv/bin/python scripts/package_offline_models.py "$@"
