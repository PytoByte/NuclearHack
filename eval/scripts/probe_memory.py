#!/usr/bin/env python3
"""Host-only model lifetime probe; malloc_trim is diagnostic, not SDK behavior."""
import argparse
import ctypes as C
import json
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from native_sdk import NativeSdk, ROOT
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import sha256


def rss():
    return int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--cycles', type=int, default=5)
    parser.add_argument('--trim', action='store_true')
    args = parser.parse_args()
    if not args.experiment.startswith('exp_') or not args.experiment[4:].isdigit() or args.cycles < 1:
        parser.error('Provide exp_NNNN and positive cycles')
    out = ROOT / '.audio-runs' / args.experiment
    out.mkdir(parents=True, exist_ok=False)
    sdk = NativeSdk()
    catalog = json.loads((ROOT / 'config/audio-models.lock.json').read_text())
    model = next(m for m in catalog['models'] if m['id'] == 'giga-v3-ctc')
    for item in catalog['files']:
        if item['path'] in model['files'] and sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError('Model hash mismatch')
    row = json.loads((ROOT / 'eval/data/fleurs-ru-validation.jsonl').read_text().splitlines()[0])
    samples = sdk.decode(ROOT / row['audio'])
    config = dict(experiment_id=args.experiment, model=model, audio=row, threads=4,
                  cycles=args.cycles, glibc_malloc_trim_diagnostic=args.trim,
                  sdk_sha256=sha256(ROOT / '.build/audio/libnuclear_audio.so'))
    (out / 'config.json').write_text(json.dumps(config, indent=2))
    trim = None
    if args.trim:
        trim = C.CDLL(None).malloc_trim
        trim.argtypes = [C.c_size_t]
        trim.restype = C.c_int
    observations = []
    for cycle in range(args.cycles):
        observation = dict(cycle=cycle + 1, before_load=rss())
        start = time.perf_counter()
        handle = sdk.create(model['family'], model['files'], 4)
        observation.update(after_load=rss(), load_seconds=time.perf_counter() - start)
        try:
            sdk.transcribe(handle, samples)
            observation['before_release'] = rss()
        finally:
            sdk.lib.nh_asr_destroy(handle)
        observation['after_release'] = rss()
        if trim:
            observation['malloc_trim_return'] = trim(0)
            observation['after_trim'] = rss()
        observations.append(observation)
        with (out / 'observations.jsonl').open('a') as log:
            log.write(json.dumps(observation) + '\n')
        print(json.dumps(observation), flush=True)
    result = dict(experiment_id=args.experiment, observations=observations,
        process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        scope='Linux glibc host-only lifetime diagnostic; not Android RSS/allocator behavior')
    (out / 'metrics.json').write_text(json.dumps(result, indent=2))
    (out / 'environment.json').write_text(json.dumps(dict(host=platform.platform(),
        git_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        git_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))), indent=2))
    summary = ROOT / 'eval/results' / args.experiment
    summary.mkdir(parents=True, exist_ok=False)
    for name in ('metrics.json', 'config.json', 'environment.json'):
        (summary / name).write_bytes((out / name).read_bytes())


if __name__ == '__main__':
    main()
