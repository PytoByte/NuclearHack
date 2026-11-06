#!/usr/bin/env python3
"""One isolated model/config screening run through the native SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time

from native_sdk import NativeSdk, ROOT
from scoring import aggregate, counts
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import sha256


def current_rss_kib():
    return int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'eval/data/fleurs-ru-validation.jsonl')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if not args.experiment.startswith('exp_') or not args.experiment[4:].isdigit():
        parser.error('Experiment ID must be exp_NNNN')
    catalog_path = ROOT / 'config/audio-models.lock.json'
    catalog = json.loads(catalog_path.read_text())
    model = next(m for m in catalog['models'] if m['id'] == args.model)
    for item in catalog['files']:
        if item['path'] in model['files'] and sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError('Invalid model file: ' + item['path'])
    manifest = args.manifest.resolve()
    dataset = [json.loads(line) for line in manifest.read_text().splitlines()]
    if args.limit:
        dataset = dataset[:args.limit]
    out = ROOT / '.audio-runs' / args.experiment
    out.mkdir(parents=True, exist_ok=False)
    # Capture native runtime diagnostics, which do not pass through Python logging.
    diagnostics = (out / 'stderr.log').open('a')
    os.dup2(diagnostics.fileno(), 2)
    def report(value):
        line = json.dumps(value)
        print(line, flush=True)
        with (out / 'stdout.log').open('a') as log:
            log.write(line + '\n')
    config = dict(experiment_id=args.experiment, model=model, threads=args.threads,
        manifest=str(manifest.relative_to(ROOT)), manifest_sha256=sha256(manifest),
        selected_audio_ids=[r['audio_id'] for r in dataset],
        normalization='v1: NFC, lowercase, yo->ye, punctuation/symbols->space; keep numbers/fillers',
        decoder='native miniaudio; 16kHz mono; original WAV',
        model_lock_sha256=sha256(catalog_path), sdk_sha256=sha256(ROOT / '.build/audio/libnuclear_audio.so'))
    config['model_files'] = [item for item in catalog['files'] if item['path'] in model['files']]
    (out / 'config.json').write_text(json.dumps(config, indent=2))
    environment = dict(git_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        git_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
        host=platform.platform(), machine=platform.machine(), python=sys.version,
        cpu_model=next((l.split(':', 1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')), 'unknown'),
        measurement_scope='Linux desktop CPU, Python harness + production C ABI; not Android')
    (out / 'environment.json').write_text(json.dumps(environment, indent=2))
    sdk = NativeSdk()
    rss_stages = dict(before_load=current_rss_kib())
    start = time.perf_counter()
    handle = sdk.create(model['family'], model['files'], args.threads)
    load_seconds = time.perf_counter() - start
    rss_stages['after_load'] = current_rss_kib()
    results = []
    try:
        with (out / 'results.jsonl').open('w') as target:
            for row in dataset:
                audio, reference = ROOT / row['audio'], ROOT / row['reference']
                if sha256(audio) != row['audio_sha256'] or sha256(reference) != row['reference_sha256']:
                    raise ValueError('Dataset checksum mismatch: ' + row['audio_id'])
                before = time.perf_counter()
                samples = sdk.decode(audio)
                decode_seconds = time.perf_counter() - before
                before = time.perf_counter()
                hypothesis = sdk.transcribe(handle, samples)
                inference_seconds = time.perf_counter() - before
                text = reference.read_text(encoding='utf-8')
                result = dict(audio_id=row['audio_id'], reference=text, hypothesis=hypothesis,
                    audio_seconds=len(samples) / 16000, decode_seconds=decode_seconds,
                    inference_seconds=inference_seconds, normalized=counts(text, hypothesis['text']),
                    raw=counts(text, hypothesis['text'], normalized=False))
                target.write(json.dumps(result, ensure_ascii=False) + '\n')
                target.flush()
                results.append(result)
                report(dict(experiment=args.experiment, done=len(results), total=len(dataset),
                    audio_id=row['audio_id'], inference_seconds=round(inference_seconds, 3)))
    except BaseException as error:
        (out / 'failure.json').write_text(json.dumps(dict(type=type(error).__name__, error=str(error), completed=len(results))))
        raise
    finally:
        rss_stages['before_release'] = current_rss_kib()
        sdk.lib.nh_asr_destroy(handle)
        rss_stages['after_release'] = current_rss_kib()
    inference = sum(r['inference_seconds'] for r in results)
    decode = sum(r['decode_seconds'] for r in results)
    duration = sum(r['audio_seconds'] for r in results)
    metrics = dict(experiment_id=args.experiment, model=args.model, threads=args.threads,
        clips=len(results), audio_seconds=duration, load_seconds=load_seconds,
        inference_seconds=inference, decode_seconds=decode, inference_rtf=inference / duration,
        full_rtf=(load_seconds + decode + inference) / duration,
        first_inference_seconds=results[0]['inference_seconds'],
        median_inference_seconds=statistics.median(r['inference_seconds'] for r in results),
        process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        current_rss_kib_by_stage=rss_stages,
        normalized=aggregate([r['normalized'] for r in results]), raw=aggregate([r['raw'] for r in results]),
        scope=environment['measurement_scope'], manifest_sha256=config['manifest_sha256'])
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=2))
    summary = ROOT / 'eval/results' / args.experiment
    summary.mkdir(parents=True, exist_ok=False)
    for name in ('metrics.json', 'config.json', 'environment.json'):
        (summary / name).write_bytes((out / name).read_bytes())
    report(metrics)


if __name__ == '__main__':
    main()
