#!/usr/bin/env python3
"""Exercise the additive streaming diarization C ABI on frozen PCM and ASR words."""
import argparse
import ctypes as C
import json
import os
import re
import resource
import sys
import time
import numpy as np
from native_sdk import ROOT, NativeSdk, record_build
from probe_sortformer import turns_from_probs
from probe_attribution import attribute
from probe_reclustering import diarization
from run_file_pipeline import cpwer
from scoring import normalize, speaker_coverage
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256


class Config(C.Structure):
    _fields_ = [('struct_size', C.c_uint32), ('model', C.c_char_p), ('threads', C.c_uint32),
                ('profile', C.c_uint32), ('max_audio_seconds', C.c_uint32)]


class Stats(C.Structure):
    _fields_ = [('struct_size', C.c_uint32), ('speaker_slots', C.c_uint32),
                ('received_samples', C.c_uint64), ('emitted_frames', C.c_uint64), ('model_calls', C.c_uint64),
                ('buffered_samples', C.c_uint64), ('peak_buffered_samples', C.c_uint64),
                ('cache_frames', C.c_uint32), ('fifo_frames', C.c_uint32), ('max_feature_frames', C.c_uint32),
                ('inference_seconds', C.c_double)]


Callback = C.CFUNCTYPE(C.c_int32, C.POINTER(C.c_float), C.c_uint32, C.c_uint32, C.c_uint64, C.c_void_p)


class Stream:
    def __init__(self, sdk, model, profile=1, max_seconds=600):
        self.sdk = sdk
        l = sdk.lib
        l.nh_streaming_diarizer_create.argtypes = [C.POINTER(Config), C.POINTER(C.c_void_p)]
        l.nh_streaming_diarizer_create.restype = C.c_int32
        l.nh_streaming_diarizer_accept.argtypes = [C.c_void_p, C.POINTER(C.c_float), C.c_uint32, Callback, C.c_void_p]
        l.nh_streaming_diarizer_accept.restype = C.c_int32
        l.nh_streaming_diarizer_flush.argtypes = [C.c_void_p, Callback, C.c_void_p]
        l.nh_streaming_diarizer_flush.restype = C.c_int32
        l.nh_streaming_diarizer_reset.argtypes = [C.c_void_p]
        l.nh_streaming_diarizer_reset.restype = C.c_int32
        l.nh_streaming_diarizer_get_stats.argtypes = [C.c_void_p, C.POINTER(Stats)]
        l.nh_streaming_diarizer_get_stats.restype = C.c_int32
        l.nh_streaming_diarizer_destroy.argtypes = [C.c_void_p]
        l.nh_onnxruntime_version.restype = C.c_char_p
        self.handle = C.c_void_p()
        config = Config(C.sizeof(Config), os.fsencode(model), 4, profile, max_seconds)
        sdk.check(l.nh_streaming_diarizer_create(C.byref(config), C.byref(self.handle)))

    def close(self):
        if self.handle:
            self.sdk.lib.nh_streaming_diarizer_destroy(self.handle)
            self.handle = C.c_void_p()

    def reset(self):
        self.sdk.check(self.sdk.lib.nh_streaming_diarizer_reset(self.handle))

    def stats(self):
        stats = Stats()
        stats.struct_size = C.sizeof(Stats)
        self.sdk.check(self.sdk.lib.nh_streaming_diarizer_get_stats(self.handle, C.byref(stats)))
        return {name: getattr(stats, name) for name, _ in Stats._fields_}

    def predict(self, pcm, block_frames):
        self.reset()
        blocks, errors, offsets = [], [], []
        received = 0

        @Callback
        def consume(data, rows, slots, start, _):
            nonlocal received
            try:
                if slots != 8 or not rows or start != received*160:
                    raise ValueError('Noncontiguous or invalid posterior delivery')
                values = np.ctypeslib.as_array(data, shape=(rows*slots,)).reshape(rows, slots).copy()
                if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1):
                    raise ValueError('Invalid posterior probability')
                blocks.append(values)
                offsets.append(dict(start_sample=start, frames=rows))
                received += rows
                return 0
            except Exception as e:
                errors.append(str(e))
                return 1

        for offset in range(0, len(pcm), block_frames):
            part = np.ascontiguousarray(pcm[offset:offset+block_frames], dtype=np.float32)
            self.sdk.check(self.sdk.lib.nh_streaming_diarizer_accept(self.handle,
                part.ctypes.data_as(C.POINTER(C.c_float)), len(part), consume, None))
        self.sdk.check(self.sdk.lib.nh_streaming_diarizer_flush(self.handle, consume, None))
        if errors:
            raise ValueError('; '.join(errors))
        values = np.concatenate(blocks) if blocks else np.empty((0, 8), np.float32)
        if len(values) != len(pcm)//160:
            raise ValueError('Source/posterior length mismatch')
        return values, offsets


def controls(sdk, model, audio, profile):
    """Real-model transport invariance and terminal-state controls, serially."""
    pcm = sdk.decode(audio, max_frames=180*16000+16)
    stream = Stream(sdk, model, profile)
    result = {}
    try:
        a, offsets_a = stream.predict(pcm, 997)
        b, offsets_b = stream.predict(pcm, 400000)
        if not np.array_equal(a, b) or offsets_a != offsets_b:
            raise ValueError('Transport partition changed posterior values/timeline')
        result['transport_partition_exact'] = dict(block_frames=[997, 400000], emitted_frames=len(a),
                                                   max_posterior_delta=float(abs(a-b).max(initial=0)))
        stream.reset()
        nested, delivered = [], []

        @Callback
        def stop(_, rows, slots, start, user):
            delivered.append(dict(frames=rows, slots=slots, start_sample=start))
            nested.append(sdk.lib.nh_streaming_diarizer_reset(stream.handle))
            return 1

        status = 0
        for offset in range(0, len(pcm), 400000):
            part = np.ascontiguousarray(pcm[offset:offset+400000], dtype=np.float32)
            status = sdk.lib.nh_streaming_diarizer_accept(stream.handle,
                part.ctypes.data_as(C.POINTER(C.c_float)), len(part), stop, None)
            if status:
                break
        if not status:
            status = sdk.lib.nh_streaming_diarizer_flush(stream.handle, stop, None)
        after = sdk.lib.nh_streaming_diarizer_flush(stream.handle, stop, None)
        if status != 4 or nested != [5] or len(delivered) != 1 or after != 1:
            raise ValueError('Cancellation/reentry/terminal state contract failed')
        result['cancel_reentry'] = dict(status=status, nested_reset_status=nested, flush_after_cancel_status=after,
                                       callbacks=delivered)
        stream.reset()
        if stream.stats()['received_samples']:
            raise ValueError('Reset retained old source samples')
    finally:
        stream.close()
    budget = Stream(sdk, model, profile, max_seconds=1)
    callbacks = []

    @Callback
    def collect(_, rows, slots, start, user):
        callbacks.append(dict(frames=rows, slots=slots, start_sample=start))
        return 0

    try:
        samples = np.zeros(16000, np.float32)
        pointer = samples.ctypes.data_as(C.POINTER(C.c_float))
        sdk.check(sdk.lib.nh_streaming_diarizer_accept(budget.handle, pointer, len(samples), collect, None))
        status = sdk.lib.nh_streaming_diarizer_accept(budget.handle, pointer, 1, collect, None)
        if status != 1 or budget.stats()['received_samples'] != 16000:
            raise ValueError('Duration limit consumed unaccepted input')
        sdk.check(sdk.lib.nh_streaming_diarizer_flush(budget.handle, collect, None))
        before = len(callbacks)
        sdk.check(sdk.lib.nh_streaming_diarizer_flush(budget.handle, collect, None))
        if before != len(callbacks) or sum(c['frames'] for c in callbacks) != 100:
            raise ValueError('Flush duplicated/missed posterior rows')
        result['duration_budget'] = dict(extra_sample_status=status, received_samples=16000, flush_idempotent=True)
        budget.reset()
        invalid = np.array([np.nan], np.float32)
        status = sdk.lib.nh_streaming_diarizer_accept(budget.handle,
            invalid.ctypes.data_as(C.POINTER(C.c_float)), 1, collect, None)
        if status != 1 or budget.stats()['received_samples']:
            raise ValueError('Invalid PCM altered source timeline')
        result['nonfinite_input_rejected_without_consumption'] = True
    finally:
        budget.close()
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True)
    p.add_argument('--baseline', default='exp_0125')
    p.add_argument('--prototype', default='exp_0165')
    p.add_argument('--manifest', default='eval/data/dialogs-smoke.jsonl')
    p.add_argument('--profile', choices=['buffered', 'low'], default='buffered')
    p.add_argument('--block-frames', type=int, default=4096)
    p.add_argument('--skip-controls', action='store_true', help='Quality-only follow-up after this profile passed transport/lifecycle controls')
    args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment) or not 1 <= args.block_frames <= 400000:
        p.error('Use exp_NNNN and block-frames in1..400000')
    out = ROOT/'.audio-runs'/args.experiment
    out.mkdir(parents=True, exist_ok=False)
    lock = json.loads((ROOT/'config/audio-models.lock.json').read_text())
    descriptor = next(m for m in lock['models'] if m['id'] == 'nemotron3-diarization-q8')
    files = [next(f for f in lock['files'] if f['path'] == path) for path in descriptor['files']]
    for item in files:
        if sha256(ROOT/item['path']) != item['sha256']:
            raise ValueError('Changed model asset')
    sdk = NativeSdk()
    config = dict(vars(args), model_files=files, manifest_sha256=sha256(ROOT/args.manifest),
                  sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'), threads=4,
                  scope='native streaming C ABI, caller retains <=180s research PCM; host, not Android/ARM qualification',
                  input_sha256={})
    record_build(out, config)
    (out/'config.json').write_text(json.dumps(config, indent=2))
    started = time.perf_counter()
    stream = Stream(sdk, ROOT/files[0]['path'], 1 if args.profile == 'buffered' else 0)
    load_seconds = time.perf_counter()-started
    config['ort_version'] = sdk.lib.nh_onnxruntime_version().decode()
    cases = []
    try:
        for f in map(json.loads, (ROOT/args.manifest).read_text().splitlines()):
            if sha256(ROOT/f['audio']) != f['audio_sha256'] or sha256(ROOT/f['reference']) != f['reference_sha256']:
                raise ValueError('Frozen corpus changed')
            path = ROOT/'.audio-runs'/args.baseline/f['audio_id']/'transcript.json.trace.json'
            config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
            trace = json.loads(path.read_text())
            pcm = sdk.decode(ROOT/f['audio'], max_frames=180*16000+16)
            if len(pcm) >= 180*16000+16:
                raise ValueError('Research clip exceeds budget')
            duration = len(pcm)/16000
            if f.get('audio_seconds') is not None and abs(duration-f['audio_seconds']) > .002:
                raise ValueError('Decoded duration differs')
            started = time.perf_counter()
            probs, offsets = stream.predict(pcm, args.block_frames)
            wall = time.perf_counter()-started
            stats = stream.stats()
            chunk, right, fifo = (340, 40, 40) if args.profile == 'buffered' else (9, 4, 264)
            if stats['received_samples'] != len(pcm) or stats['emitted_frames'] != len(probs) or stats['cache_frames'] > 264 or stats['fifo_frames'] > fifo or stats['max_feature_frames'] > (chunk+right)*8 or stats['peak_buffered_samples'] > (chunk+right)*8*160+241:
                raise ValueError('Native stream violates its declared source/state budget')
            turns = turns_from_probs(probs, duration, resolution_ms=10)
            utterances = attribute(trace['words'], turns)
            if normalize(' '.join(t['text'] for t in utterances)) != normalize(' '.join(w['text'] for w in trace['words'])):
                raise ValueError('Changed ASR lexical sequence')
            truth = json.loads((ROOT/f['reference']).read_text())['transcript']
            case = dict(audio_id=f['audio_id'], audio_seconds=duration, wall_seconds=wall, inference_rtf=wall/duration,
                        speaker_attributed=cpwer(truth, utterances), **speaker_coverage(utterances), native_stats=stats,
                        process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            if f.get('rttm'):
                case.update(diarization(truth, turns, duration))
            prototype = ROOT/'.audio-runs'/args.prototype/(f['audio_id']+'.probs.npy')
            if prototype.exists():
                config['input_sha256'][str(prototype.relative_to(ROOT))] = sha256(prototype)
                original = np.load(prototype)
                if original.shape != probs.shape:
                    raise ValueError('Native/prototype time grids differ')
                case['prototype_comparison'] = dict(max_posterior_delta=float(abs(original-probs).max(initial=0)),
                    threshold_flips=int(((original>.5)!=(probs>.5)).sum()))
            np.save(out/(f['audio_id']+'.probs.npy'), probs)
            (out/(f['audio_id']+'.trace.json')).write_text(json.dumps(dict(turns=turns, utterances=utterances, callbacks=offsets), indent=2))
            cases.append(case)
            print(json.dumps(case), flush=True)
    finally:
        stream.close()
    first = json.loads((ROOT/args.manifest).read_text().splitlines()[0])
    control_metrics = dict(skipped='explicit quality-only follow-up') if args.skip_controls else controls(sdk, ROOT/files[0]['path'], ROOT/first['audio'], 1 if args.profile == 'buffered' else 0)
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], load_seconds=load_seconds, cases=cases,
                   controls=control_metrics,
                   cpwer=sum(c['speaker_attributed']['errors'] for c in cases)/sum(c['speaker_attributed']['reference_words'] for c in cases),
                   inference_rtf=sum(c['wall_seconds'] for c in cases)/sum(c['audio_seconds'] for c in cases),
                   process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    report = ROOT/'eval/results'/args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2))
        (report/name).write_bytes((out/name).read_bytes())


if __name__ == '__main__':
    main()
