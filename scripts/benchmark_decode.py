#!/usr/bin/env python3
"""Measure native decoder wall time and peak RSS on Linux, not model inference."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if len(sys.argv) != 2 or platform.system() != 'Linux':
    raise SystemExit('Usage on Linux: python3 scripts/benchmark_decode.py LOCAL_AUDIO')
run_id = datetime.now(timezone.utc).strftime('decode-%Y%m%dT%H%M%S.%fZ')
out = ROOT / '.audio-runs' / run_id
out.mkdir(parents=True)
with (out / 'stdout.log').open('wb') as stdout, (out / 'stderr.log').open('wb') as stderr:
    started = time.monotonic()
    child = subprocess.Popen([str(ROOT / '.build/audio/nh-audio'), 'probe', sys.argv[1]],
                             stdout=stdout, stderr=stderr)
    _, status, usage = os.wait4(child.pid, 0)
    child.returncode = os.waitstatus_to_exitcode(status)
    elapsed = time.monotonic() - started
if child.returncode:
    raise SystemExit(f'Decoder failed ({child.returncode}); logs: {out}')
metrics = json.loads((out / 'stdout.log').read_text())
metrics.update(run_id=run_id, host=platform.platform(), cpu=platform.machine(),
               git_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               git_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
               process_wall_seconds=elapsed, process_peak_rss_kib=usage.ru_maxrss)
(out / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
print(json.dumps(metrics, indent=2))
print(f'Logs: {out}')
