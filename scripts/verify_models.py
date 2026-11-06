#!/usr/bin/env python3
from pathlib import Path
import sys
from audio_tools import models
models(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'config/audio-models.lock.json')
