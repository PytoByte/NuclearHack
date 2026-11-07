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
import jiwer

from native_sdk import NativeSdk, ROOT, record_build
from scoring import aggregate, counts, normalize
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import sha256


def current_rss_kib():
    return int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--method', choices=['greedy_search','modified_beam_search'], default='greedy_search')
    parser.add_argument('--language', default='ru', help='Empty string requests Whisper autodetect')
    parser.add_argument('--hotwords', type=Path)
    parser.add_argument('--vad',action='store_true')
    parser.add_argument('--vad-threshold',type=float,default=0.5)
    parser.add_argument('--padding-ms',type=int,default=250)
    parser.add_argument('--min-speech',type=float,default=0.1)
    parser.add_argument('--min-silence',type=float,default=0.3)
    parser.add_argument('--chunk-seconds',type=int,default=25)
    parser.add_argument('--gain-db',type=float,default=0)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'eval/data/fleurs-ru-validation.jsonl')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if not 1<=args.chunk_seconds<=25 or not 0<=args.padding_ms<=2000:parser.error('Invalid chunk/padding budget')
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
        decoding_method=args.method, language=args.language,
        hotwords_sha256=sha256(args.hotwords) if args.hotwords else None,
        vad=args.vad,vad_threshold=args.vad_threshold,padding_ms=args.padding_ms,min_speech=args.min_speech,
        min_silence=args.min_silence,chunk_seconds=args.chunk_seconds,gain_db=args.gain_db,
        manifest=str(manifest.relative_to(ROOT)), manifest_sha256=sha256(manifest),
        selected_audio_ids=[r['audio_id'] for r in dataset],
        normalization='v1: NFC, lowercase, yo->ye, punctuation/symbols->space; keep numbers/fillers',
        decoder='native miniaudio; 16kHz mono; original WAV',
        model_lock_sha256=sha256(catalog_path), sdk_sha256=sha256(ROOT / '.build/audio/libnuclear_audio.so'))
    config['model_files'] = [item for item in catalog['files'] if item['path'] in model['files']]
    record_build(out,config)
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
    handle = sdk.create(model['family'], model['files'], args.threads, args.method, args.language, args.hotwords)
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
                if args.gain_db:samples=samples*(10**(args.gain_db/20))
                before = time.perf_counter()
                regions,raw_regions = sdk.speech_regions(samples,args.vad_threshold,args.padding_ms,args.min_speech,args.min_silence) if args.vad else ([(0,len(samples))],[])
                vad_seconds=time.perf_counter()-before
                chunks=[]
                for start,end in regions:
                    for offset in range(start,end,args.chunk_seconds*16000):
                        stop=min(end,offset+args.chunk_seconds*16000)
                        value=sdk.transcribe(handle,samples[offset:stop]);chunks.append(dict(offset_frames=offset,end_frame=stop,**value))
                hypothesis=dict(text=' '.join(c['text'] for c in chunks),backend=chunks)
                inference_seconds = time.perf_counter() - before
                text = reference.read_text(encoding='utf-8')
                characters=jiwer.process_characters(normalize(text),normalize(hypothesis['text']))
                result = dict(audio_id=row['audio_id'], reference=text, hypothesis=hypothesis,
                    character_errors=characters.substitutions+characters.deletions+characters.insertions,
                    reference_characters=characters.hits+characters.substitutions+characters.deletions,
                    audio_seconds=len(samples) / 16000, decode_seconds=decode_seconds,
                    inference_seconds=inference_seconds, normalized=counts(text, hypothesis['text']),
                    vad_seconds=vad_seconds,vad_regions=raw_regions,padded_regions=regions,
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
        cer=sum(r['character_errors'] for r in results)/sum(r['reference_characters'] for r in results),
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
