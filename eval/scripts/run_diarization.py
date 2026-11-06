#!/usr/bin/env python3
"""A real native diarization run scored against publisher annotations."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from native_sdk import NativeSdk, ROOT, TURN, DiarConfig
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--quant', choices=['fp32', 'int8'], default='fp32')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--threshold', type=float, default=0.5)
    parser.add_argument('--embedding', choices=['eres2net','wespeaker-resnet34-lm'], default='eres2net')
    parser.add_argument('--min-on', type=float, default=0.3)
    parser.add_argument('--min-off', type=float, default=0.5)
    parser.add_argument('--oracle-speakers', type=int, default=-1)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'eval/data/ami-diarization-smoke.json')
    args = parser.parse_args()
    if not args.experiment.startswith('exp_') or not args.experiment[4:].isdigit():
        parser.error('Experiment ID must be exp_NNNN')
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text())
    catalog = json.loads((ROOT / 'config/audio-models.lock.json').read_text())
    model = next(m for m in catalog['models'] if m['id'] == 'pyannote-eres2net-' + args.quant)
    if args.embedding != 'eres2net':
        model = dict(model, files=[p for p in model['files'] if '/embedding.' not in p] +
            next(m['files'] for m in catalog['models'] if m['id']==args.embedding))
    for item in catalog['files']:
        if item['path'] in model['files'] and sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError('Invalid diarization model file: ' + item['path'])
    for name in ('audio', 'reference'):
        if sha256(ROOT / manifest[name]) != manifest[name + '_sha256']:
            raise ValueError('Invalid AMI input/reference')
    out = ROOT / '.audio-runs' / args.experiment
    out.mkdir(parents=True, exist_ok=False)
    diagnostics = (out / 'stderr.log').open('a')
    os.dup2(diagnostics.fileno(), 2)
    config = dict(experiment_id=args.experiment, model=model, threads=args.threads, threshold=args.threshold,
        embedding=args.embedding, min_duration_on=args.min_on, min_duration_off=args.min_off, oracle_speakers=args.oracle_speakers,
        collar_seconds=0.25, skip_overlap=False, uem=[0, 180],
        manifest=manifest, manifest_sha256=sha256(manifest_path), sdk_sha256=sha256(ROOT / '.build/audio/libnuclear_audio.so'))
    (out / 'config.json').write_text(json.dumps(config, indent=2))
    sdk = NativeSdk()
    lib = sdk.lib
    lib.nh_diarizer_create.argtypes = [C.c_char_p, C.c_char_p, C.c_uint32, C.c_float, C.POINTER(C.c_void_p)]
    lib.nh_diarizer_process.argtypes = [C.c_void_p, C.POINTER(C.c_float), C.c_uint32, TURN, C.c_void_p]
    lib.nh_diarizer_destroy.argtypes = [C.c_void_p]
    segmentation = ROOT / 'models/diarization' / ('segmentation-model.onnx' if args.quant == 'fp32' else 'segmentation-model.int8.onnx')
    handle = C.c_void_p()
    before = time.perf_counter()
    lib.nh_diarizer_create_config.argtypes=[C.POINTER(DiarConfig),C.POINTER(C.c_void_p)]
    options=DiarConfig(C.sizeof(DiarConfig),os.fsencode(segmentation),os.fsencode(ROOT / 'models/diarization' /
        ('embedding.onnx' if args.embedding=='eres2net' else args.embedding+'.onnx')),
        args.threads,args.threshold,args.min_on,args.min_off,args.oracle_speakers)
    sdk.check(lib.nh_diarizer_create_config(C.byref(options),C.byref(handle)))
    load = time.perf_counter() - before
    turns = []
    @TURN
    def consume(speaker, start, end, user):
        turns.append(dict(speaker=str(speaker), start=start, end=end))
        return 0
    try:
        samples = sdk.decode(ROOT / manifest['audio'])
        before = time.perf_counter()
        sdk.check(lib.nh_diarizer_process(handle, samples.ctypes.data_as(C.POINTER(C.c_float)), len(samples), consume, None))
        elapsed = time.perf_counter() - before
        # Measure before importing the independent metric stack.
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    finally:
        lib.nh_diarizer_destroy(handle)
    (out / 'turns.json').write_text(json.dumps(turns, indent=2))
    (out / 'inference.json').write_text(json.dumps(dict(load_seconds=load,
        inference_seconds=elapsed, process_peak_rss_kib=peak, frames=len(samples)), indent=2))
    from pyannote.core import Annotation, Segment, Timeline
    from pyannote.metrics.diarization import DiarizationErrorRate, JaccardErrorRate
    reference = Annotation(uri=manifest['audio_id'])
    hypothesis = Annotation(uri=manifest['audio_id'])
    truth = json.loads((ROOT / manifest['reference']).read_text())
    for i, turn in enumerate(truth):
        reference[Segment(turn['start'], turn['end']), i] = turn['speaker']
    for i, turn in enumerate(turns):
        hypothesis[Segment(turn['start'], turn['end']), i] = turn['speaker']
    metric = DiarizationErrorRate(collar=0.25, skip_overlap=False)
    score = metric(reference, hypothesis, uem=Timeline([Segment(0, 180)]), detailed=True)
    jer=JaccardErrorRate(collar=0.25,skip_overlap=False)(reference,hypothesis,uem=Timeline([Segment(0,180)]))
    result = dict(experiment_id=args.experiment, quant=args.quant, threads=args.threads,
        jer=float(jer), embedding=args.embedding, min_duration_on=args.min_on, min_duration_off=args.min_off, oracle_speakers=args.oracle_speakers,
        threshold=args.threshold, seconds=len(samples) / 16000, load_seconds=load,
        inference_seconds=elapsed, inference_rtf=elapsed / (len(samples) / 16000),
        process_peak_rss_kib=peak, predicted_speakers=len({t['speaker'] for t in turns}),
        reference_speakers=len({t['speaker'] for t in truth}), segments=len(turns),
        der_details={k: float(v) for k, v in score.items()}, dataset_split=manifest['source_split'],
        scope='Linux CPU / one English AMI IHM excerpt; not Russian/Android')
    (out / 'metrics.json').write_text(json.dumps(result, indent=2))
    (out / 'environment.json').write_text(json.dumps(dict(host=platform.platform(),
        git_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        git_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))), indent=2))
    summary = ROOT / 'eval/results' / args.experiment
    summary.mkdir(parents=True, exist_ok=False)
    for name in ('metrics.json', 'config.json', 'environment.json'):
        (summary / name).write_bytes((out / name).read_bytes())
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
