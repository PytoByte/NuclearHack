#!/usr/bin/env python3
"""Borrow native causal enhancement only before ASR; paired lexical evaluation.

Raw audio remains the intended diarization source. This probe does not generate
new word timing/DER claims. Both ASR paths use the same native CTC/chunk policy.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sys
import time
import numpy as np
from native_sdk import ROOT, NativeSdk, record_build
from scoring import text_metrics
from compare_punctuation import summarize
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256


class GT(C.Structure): _fields_ = [('model', C.c_char_p)]
class DF(C.Structure): _fields_ = [('model', C.c_char_p), ('attenuation_limit_db', C.c_float)]
class Vox(C.Structure): _fields_ = [(k, C.c_char_p) for k in ['enroll_model', 'chunk_model', 'voice_sample']]
class Denoiser(C.Structure):
    _fields_ = [('gtcrn', GT), ('num_threads', C.c_int32), ('debug', C.c_int32), ('provider', C.c_char_p), ('dpdfnet', DF), ('voxlock', Vox)]
class Audio(C.Structure): _fields_ = [('samples', C.POINTER(C.c_float)), ('n', C.c_int32), ('sample_rate', C.c_int32)]


def chunk_ranges(frames, chunk=320000):
    offset = 0
    while offset < frames:
        remaining = frames-offset; requested = chunk
        if remaining > requested and remaining-requested < 16000 and requested > 16000:
            requested = remaining-16000
        size = min(remaining, requested)
        yield offset, size
        offset += size


def enhance(sdk, samples, path):
    import onnx
    metadata = {p.key:p.value for p in onnx.load(str(path), load_external_data=False).metadata_props}
    hop = int(metadata['hop_length']); delay = 2*int(metadata['window_length'])
    padding = delay+(-len(samples))%hop
    padded = np.pad(samples, (0, padding))
    l = sdk.lib
    l.SherpaOnnxCreateOfflineSpeechDenoiser.argtypes = [C.POINTER(Denoiser)]
    l.SherpaOnnxCreateOfflineSpeechDenoiser.restype = C.c_void_p
    l.SherpaOnnxDestroyOfflineSpeechDenoiser.argtypes = [C.c_void_p]
    l.SherpaOnnxOfflineSpeechDenoiserRun.argtypes = [C.c_void_p, C.POINTER(C.c_float), C.c_int32, C.c_int32]
    l.SherpaOnnxOfflineSpeechDenoiserRun.restype = C.POINTER(Audio)
    l.SherpaOnnxDestroyDenoisedAudio.argtypes = [C.POINTER(Audio)]
    cfg = Denoiser(); cfg.num_threads = 4; cfg.provider = b'cpu'; cfg.dpdfnet.model = os.fsencode(path)
    began = time.perf_counter(); handle = l.SherpaOnnxCreateOfflineSpeechDenoiser(C.byref(cfg))
    load = time.perf_counter()-began
    if not handle: raise RuntimeError('Native DPDFNet constructor failed')
    try:
        began = time.perf_counter()
        result = l.SherpaOnnxOfflineSpeechDenoiserRun(handle, padded.ctypes.data_as(C.POINTER(C.c_float)), len(padded), 16000)
        if not result: raise RuntimeError('Native DPDFNet inference failed')
        try:
            generated = result.contents.n
            if generated < len(samples) or abs(generated-len(padded)) > hop or result.contents.sample_rate != 16000:
                raise ValueError(f'Unexpected DSP output grid: {generated} vs padded {len(padded)}, source {len(samples)}')
            enhanced = np.ctypeslib.as_array(result.contents.samples, shape=(generated,))[:len(samples)].copy()
            if not np.isfinite(enhanced).all(): raise ValueError('Enhancement produced non-finite PCM')
        finally: l.SherpaOnnxDestroyDenoisedAudio(result)
        return enhanced, dict(load_seconds=load, processing_seconds=time.perf_counter()-began,
                              attenuation_limit_db=0, source_samples_equal=True, input_right_padding_samples=padding,
                              native_delay_compensation_samples=delay, denoiser_output_samples=generated, final_samples=len(enhanced))
    finally: l.SherpaOnnxDestroyOfflineSpeechDenoiser(handle)


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--experiment', required=True)
    p.add_argument('--manifest', default='eval/data/dialogs-smoke.jsonl'); args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment): p.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment; out.mkdir(parents=True, exist_ok=False)
    lock = json.loads((ROOT/'config/audio-models.lock.json').read_text())
    model = next(m for m in lock['models'] if m['id'] == 'giga-v3-ctc')
    asr_paths = model.get('runtime_files', model['files'])
    paths = [next(x for x in asr_paths if x.endswith('/model.int8.onnx')), next(x for x in model['files'] if x.endswith('/tokens.txt')),
             'models/dpdfnet/baseline.onnx']
    files = [next(f for f in lock['files'] if f['path'] == path) for path in paths]
    for f in files:
        if sha256(ROOT/f['path']) != f['sha256']: raise ValueError('Changed pinned block')
    config = dict(vars(args), model_files=files, model_lock_sha256=sha256(ROOT/'config/audio-models.lock.json'),
        manifest_sha256=sha256(ROOT/args.manifest), sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),
        source_url='https://k2-fsa.github.io/sherpa/onnx/speech-enhancement/dpdfnet.html', threads=4, chunk_seconds=20,
        scope='paired native DPDFNet enhancement -> native GigaAM CTC, x86 host, lexical text only; not target RAM/diarization',
        input_sha256={}, source_grid_policy='explicit right padding: two window lengths for native DSP delay + hop alignment; validate padded output then crop declared right padding, preserve exactly original source sample count')
    record_build(out, config); (out/'config.json').write_text(json.dumps(config, indent=2))
    sdk = NativeSdk(); cases = []
    for f in map(json.loads, (ROOT/args.manifest).read_text().splitlines()):
        ident = f['audio_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', ident): raise ValueError('Invalid audio ID')
        for field in ['audio', 'reference']:
            if sha256(ROOT/f[field]) != f[field+'_sha256']: raise ValueError('Changed frozen fixture')
        raw = sdk.decode(ROOT/f['audio'], max_frames=180*16000+16)
        if len(raw) >= 180*16000+16: raise ValueError('Research PCM exceeds180s')
        enhanced, denoise = enhance(sdk, raw, ROOT/paths[2])
        truth = ' '.join(t['text'] for t in json.loads((ROOT/f['reference']).read_text())['transcript'])
        folder = out/ident; folder.mkdir(); variants = {}
        for name, pcm in [('raw', raw), ('enhanced', enhanced)]:
            began = time.perf_counter(); handle = sdk.create('ctc', paths[:2], 4); load = time.perf_counter()-began
            chunks = []; began = time.perf_counter()
            try:
                for start, size in chunk_ranges(len(pcm)):
                    chunks.append(dict(offset=start, frames=size, **sdk.transcribe(handle, pcm[start:start+size])))
            finally: sdk.lib.nh_asr_destroy(handle)
            elapsed = time.perf_counter()-began; text = ' '.join(c['text'] for c in chunks)
            variants[name] = dict(text_metrics=text_metrics(truth, text), load_seconds=load,
                processing_seconds=elapsed, pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
                chunk_ranges=[[c['offset'], c['frames']] for c in chunks])
            (folder/(name+'.asr.json')).write_text(json.dumps(dict(text=text, chunks=chunks), indent=2))
        if variants['raw']['chunk_ranges'] != variants['enhanced']['chunk_ranges']: raise ValueError('ASR chunk policy differs')
        cases.append(dict(audio_id=ident, audio_seconds=len(raw)/16000, denoiser=denoise, variants=variants))
        print(json.dumps(dict(audio_id=ident, variants={k:v['text_metrics']['normalized'] for k,v in variants.items()})), flush=True)
    combined = {name:summarize([c['variants'][name]['text_metrics'] for c in cases]) for name in ['raw', 'enhanced']}
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases, variants=combined,
                   process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    report = ROOT/'eval/results'/args.experiment; report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2)); (report/name).write_bytes((out/name).read_bytes())


if __name__ == '__main__': main()
