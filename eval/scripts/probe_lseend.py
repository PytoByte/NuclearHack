#!/usr/bin/env python3
"""Screen a different streaming diarization block, using pinned publisher code.

The worker runs in the isolated frontend-reference environment, never the SDK.
No reference speaker count or words enter inference. Full vs fragmented input
is measured explicitly because the export's metadata FFT differs from its code.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def worker(args):
    import resource
    import numpy as np
    import onnxruntime as ort
    import soundfile as sf
    import librosa
    directory = ROOT/'models/lseend-dih3'
    sys.path.insert(0, str(directory/'reference'))
    import ls_eend_onnx_runtime as reference
    metadata = json.loads((directory/'ls_eend_dih3_step.json').read_text())
    start = time.perf_counter()
    # Keep all publisher feature/state algorithms; only fix the CPU thread count.
    engine = reference.ONNXLSEENDInferenceEngine.__new__(reference.ONNXLSEENDInferenceEngine)
    engine.onnx_model_path = directory/'ls_eend_dih3_step.onnx'
    engine.metadata = metadata
    engine.config = reference.config_from_metadata(metadata)
    engine.layout = reference._layout_from_metadata(metadata)
    engine.decode_max_nspks = engine.layout.max_nspks
    engine.target_sample_rate = int(metadata['sample_rate'])
    engine.model_frame_hz = reference.frame_hz(engine.config)
    engine.providers = ['CPUExecutionProvider']
    options = ort.SessionOptions(); options.intra_op_num_threads = 4; options.inter_op_num_threads = 1
    engine.session = ort.InferenceSession(str(engine.onnx_model_path), sess_options=options, providers=engine.providers)
    engine.output_names = [o.name for o in engine.session.get_outputs()]
    load_seconds = time.perf_counter()-start
    # infer_audio/create_session use the same predictor; count all preview calls too.
    calls = 0; inference_seconds = 0
    original = engine._predict_step
    def predict(*pos, **kw):
        nonlocal calls, inference_seconds
        began = time.perf_counter(); result = original(*pos, **kw)
        inference_seconds += time.perf_counter()-began; calls += 1
        return result
    engine._predict_step = predict
    audio, rate = sf.read(args.audio, dtype='float32')
    audio = reference.ensure_mono(audio)
    original_samples = len(audio)
    if rate != engine.target_sample_rate:
        audio = librosa.resample(audio, orig_sr=rate, target_sr=engine.target_sample_rate).astype(np.float32)
    source_duration = original_samples/rate
    began = time.perf_counter()
    controls = None
    if args.transport_samples:
        session = engine.create_session(engine.target_sample_rate)
        for offset in range(0, len(audio), args.transport_samples):
            session.push_audio(audio[offset:offset+args.transport_samples])
        session.finalize(); result = session.snapshot()
        actual_fft = session.feature_extractor.n_fft
    else:
        result = engine.infer_audio(audio, engine.target_sample_rate)
        actual_fft = 1 << (metadata['win_length']-1).bit_length()
    processing_seconds = time.perf_counter()-began
    probabilities = result.probabilities
    if probabilities.ndim != 2 or probabilities.shape[1] != 10 or not np.isfinite(probabilities).all():
        raise ValueError('Invalid LS-EEND output')
    np.save(args.posterior, probabilities)
    state_bytes = sum(np.prod(shape)*4 for shape in metadata['state_shapes'].values())
    measured = dict(source_duration=source_duration, original_samples=original_samples, original_rate=rate,
        model_rate=engine.target_sample_rate, posterior_frames=len(probabilities), frame_hz=result.frame_hz,
        model_slots=10, state_bytes=int(state_bytes), load_seconds=load_seconds, processing_seconds=processing_seconds,
        model_calls=calls, inference_seconds=inference_seconds, actual_fft=actual_fft, metadata_fft=metadata['n_fft'],
        transport_samples=args.transport_samples, previews_included=bool(args.transport_samples),
        process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        ort_version=ort.__version__, librosa_version=librosa.__version__, numpy_version=np.__version__)
    Path(args.measured).write_text(json.dumps(measured, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment')
    p.add_argument('--manifest', default='eval/data/dialogs-smoke.jsonl')
    p.add_argument('--baseline', default='exp_0125')
    p.add_argument('--transport-samples', type=int, default=0)
    p.add_argument('--compare')
    p.add_argument('--worker', action='store_true')
    p.add_argument('--audio'); p.add_argument('--posterior'); p.add_argument('--measured')
    args = p.parse_args()
    if args.worker:
        worker(args); return
    import os
    import re
    import subprocess
    import numpy as np
    from native_sdk import record_harness
    from scoring import normalize, speaker_coverage
    from probe_attribution import attribute
    from probe_sortformer import turns_from_probs
    from probe_reclustering import diarization
    from run_file_pipeline import cpwer
    sys.path.insert(0, str(ROOT/'scripts'))
    from bootstrap_models import sha256
    if not args.experiment or not re.fullmatch(r'exp_[0-9]+', args.experiment): p.error('Use exp_NNNN')
    if args.transport_samples < 0: p.error('Nonnegative transport samples required')
    out = ROOT/'.audio-runs'/args.experiment; out.mkdir(parents=True, exist_ok=False)
    lock = json.loads((ROOT/'config/audio-models.lock.json').read_text())
    model = next(m for m in lock['models'] if m['id'] == 'lseend-dih3-onnx')
    files = [next(f for f in lock['files'] if f['path'] == path) for path in model['files']]
    for f in files:
        if sha256(ROOT/f['path']) != f['sha256']: raise ValueError('Changed LS-EEND asset')
    config = dict(vars(args), model_files=files, model_lock_sha256=sha256(ROOT/'config/audio-models.lock.json'),
        manifest_sha256=sha256(ROOT/args.manifest), threads=4, postprocessing='threshold .5; merge gaps<500ms before drop spans<300ms',
        scope='publisher LS-EEND ONNX frontend/state reference, Python x86 host; frozen GigaAM words; not SDK/Android performance',
        input_sha256={}, frontend_note='publisher feature.py actually FFT256, metadata advertises1024; do not silently substitute frontend')
    record_harness(out, config); (out/'config.json').write_text(json.dumps(config, indent=2))
    cases = []
    for f in map(json.loads, (ROOT/args.manifest).read_text().splitlines()):
        ident = f['audio_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', ident): raise ValueError('Invalid audio ID')
        for field in ['audio', 'reference']:
            if sha256(ROOT/f[field]) != f[field+'_sha256']: raise ValueError('Changed source fixture')
        trace = ROOT/'.audio-runs'/args.baseline/ident/'transcript.json.trace.json'
        config['input_sha256'][str(trace.relative_to(ROOT))] = sha256(trace)
        words = json.loads(trace.read_text())['words']
        truth = json.loads((ROOT/f['reference']).read_text())['transcript']
        folder = out/ident; folder.mkdir()
        command = [str(ROOT/'.tools/frontend-env/bin/python'), str(Path(__file__).resolve()), '--worker', '--audio', str(ROOT/f['audio']),
            '--posterior', str(folder/'posteriors.npy'), '--measured', str(folder/'measured.json'), '--transport-samples', str(args.transport_samples)]
        (folder/'command.json').write_text(json.dumps(command, indent=2))
        env = dict(os.environ, MPLBACKEND='Agg', NUMBA_NUM_THREADS='1')
        began = time.perf_counter()
        with (folder/'stdout.log').open('w') as stdout, (folder/'stderr.log').open('w') as stderr:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, env=env, timeout=600)
        if result.returncode: raise RuntimeError('LS-EEND child failed; raw logs retained')
        elapsed = time.perf_counter()-began
        measured = json.loads((folder/'measured.json').read_text())
        probs = np.load(folder/'posteriors.npy')
        duration = measured['source_duration']
        if abs(duration-probs.shape[0]/10) > .11: raise ValueError('LS-EEND source grid mismatch')
        turns = turns_from_probs(probs, duration, resolution_ms=100)
        utterances = attribute(words, turns)
        if normalize(' '.join(t['text'] for t in utterances)) != normalize(' '.join(w['text'] for w in words)):
            raise ValueError('Attribution changed GigaAM words')
        case = dict(audio_id=ident, **measured, audio_seconds=duration, wall_seconds=elapsed,
            processing_rtf=measured['processing_seconds']/duration, speaker_attributed=cpwer(truth, utterances), **speaker_coverage(utterances))
        if f.get('rttm'): case.update(diarization(truth, turns, duration))
        if args.compare:
            previous = ROOT/'.audio-runs'/args.compare/ident/'posteriors.npy'
            config['input_sha256'][str(previous.relative_to(ROOT))] = sha256(previous)
            prior = np.load(previous)
            case['transport_comparison'] = dict(reference=args.compare, shape_equal=prior.shape == probs.shape)
            if prior.shape == probs.shape:
                case['transport_comparison'].update(max_delta=float(abs(prior-probs).max(initial=0)), threshold_flips=int(((prior>.5)!=(probs>.5)).sum()))
        (folder/'trace.json').write_text(json.dumps(dict(turns=turns, utterances=utterances), indent=2))
        cases.append(case)
        print(json.dumps(dict(audio_id=ident, cpwer=case['speaker_attributed']['cpwer'], processing_rtf=case['processing_rtf'])), flush=True)
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases,
        cpwer=sum(c['speaker_attributed']['errors'] for c in cases)/sum(c['speaker_attributed']['reference_words'] for c in cases),
        inference_rtf=sum(c['processing_seconds'] for c in cases)/sum(c['audio_seconds'] for c in cases),
        process_peak_rss_kib=max(c['process_peak_rss_kib'] for c in cases))
    report = ROOT/'eval/results'/args.experiment; report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2)); (report/name).write_bytes((out/name).read_bytes())


if __name__ == '__main__': main()
