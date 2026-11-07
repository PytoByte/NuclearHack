#!/usr/bin/env python3
"""Fetch hash-pinned self-contained NeMo clustering code, research only."""
import json
from bootstrap_audio import ROOT, install


def main():
    lock = json.loads((ROOT/'config/audio-toolchain.lock.json').read_text())
    spec = next(a for a in lock['research_artifacts'] if a['name'] == 'research/nmesc/offline_clustering.py')
    install(spec)
    print('Verified NeMo clustering reference; uses isolated frontend-env Torch')


if __name__ == '__main__': main()
