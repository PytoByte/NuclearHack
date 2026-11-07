#!/usr/bin/env python3
"""Bounded-window CPU Sortformer research; preserved ASR words, automatic <=4 slots.

Frontend/state equations follow NVIDIA NeMo (Apache-2.0), revision recorded below.
This independent NumPy implementation has not established NeMo numerical parity.
No reference speaker counts, turns, or text enter inference or cache management.
"""
import argparse
import json
import math
import re
import resource
import sys
import time
import numpy as np
import onnxruntime as ort
from scipy.fft import rfft
from native_sdk import ROOT, NativeSdk, record_build
from probe_attribution import attribute
from probe_reclustering import diarization
from run_file_pipeline import cpwer
from scoring import normalize, speaker_coverage
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import sha256

NEMO_REV = 'cd61689d41b1962d3e1957ae8faf28bf8bee0e3b'
PROFILES = {'low': (6, 7, 188, 144), 'buffered': (340, 40, 40, 300)}


def mel_features(pcm):
    """128 Slaney filters, symmetric Hann400/FFT512/hop160, no normalization.

    Dither disabled deliberately for reproducibility; no bfloat16 rounding.
    Centered STFT has 16ms acoustic lookahead, covered by explicit right context.
    """
    x = np.asarray(pcm, dtype=np.float32)
    if not len(x):
        return np.empty((0, 128), dtype=np.float32)
    x = np.concatenate([x[:1], x[1:] - np.float32(.97)*x[:-1]])
    padded = np.pad(x, (256, 256))
    frames = np.lib.stride_tricks.sliding_window_view(padded, 512)[::160]
    window = np.pad(np.hanning(400).astype(np.float32), (56, 56))
    power = np.abs(rfft(frames*window, axis=1))**2
    # Slaney's linear region below 1kHz, logarithmic region above it.
    maximum = 15 + math.log(8) / (math.log(6.4)/27)
    mels = np.linspace(0, maximum, 130)
    hz = mels*(200/3)
    high = mels >= 15
    hz[high] = 1000*np.exp((mels[high]-15)*(math.log(6.4)/27))
    freqs = np.arange(257)*16000/512
    lower = (freqs[None, :]-hz[:-2, None])/np.diff(hz)[:-1, None]
    upper = (hz[2:, None]-freqs[None, :])/np.diff(hz)[1:, None]
    filters = (np.maximum(0, np.minimum(lower, upper))*(2/(hz[2:]-hz[:-2]))[:, None]).astype(np.float32)
    features = np.log(power @ filters.T + np.float32(2**-24))
    # NeMo's reported valid length excludes the extra centered frame.
    return np.ascontiguousarray(features[:len(pcm)//160], dtype=np.float32)


class Sortformer:
    def __init__(self, model, profile):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), options, providers=['CPUExecutionProvider'])
        self.chunk, self.right, self.fifo_cap, self.update = PROFILES[profile]
        self.reset()

    def reset(self):
        self.cache = np.empty((0, 512), np.float32)
        self.fifo = np.empty((0, 512), np.float32)
        self.cache_probs = np.empty((0, 4), np.float32)
        self.compressed = False
        self.silence_sum = np.zeros(512, np.float64)
        self.silence_count = 0
        self.steps = []

    def compress(self):
        probs = self.cache_probs
        log_p = np.log(np.maximum(probs, .25))
        log_q = np.log(np.maximum(1-probs, .25))
        scores = log_p-log_q+log_q.sum(axis=1, keepdims=True)-np.log(.5)
        per_speaker = 188//4-3
        positive = ((scores > 0) & (probs > .5)).sum(axis=0)
        scores[(probs <= .5) | ((scores <= 0) & (positive >= math.floor(per_speaker*.5))[None, :])] = -np.inf
        scores[188:] += .05
        for count, boost in [(math.floor(per_speaker*.75), 2), (math.floor(per_speaker*1.5), 1)]:
            for speaker in range(4):
                indices = np.argsort(-scores[:, speaker], kind='stable')[:count]
                scores[indices, speaker] -= boost*np.log(.5)
        scores = np.concatenate([scores, np.full((3, 4), np.inf, np.float32)])
        flat = scores.T.reshape(-1)
        chosen = np.argsort(-flat, kind='stable')[:188]
        chosen[np.isneginf(flat[chosen])] = 99999
        chosen.sort()
        frames = chosen % len(scores)
        disabled = (chosen == 99999) | (frames >= len(self.cache))
        frames[disabled] = 0
        self.cache = self.cache[frames].copy()
        self.cache_probs = probs[frames].copy()
        silence = self.silence_sum/max(1, self.silence_count)
        self.cache[disabled] = silence
        self.cache_probs[disabled] = 0
        self.compressed = True

    def step(self, features, left, keep):
        cache_len, fifo_len = len(self.cache), len(self.fifo)
        inputs = dict(chunk=features[None], chunk_lengths=np.array([len(features)], np.int64),
                      spkcache=self.cache[None], spkcache_lengths=np.array([cache_len], np.int64),
                      fifo=self.fifo[None], fifo_lengths=np.array([fifo_len], np.int64))
        started = time.perf_counter()
        probs, embeddings, lengths = self.session.run(None, inputs)
        seconds = time.perf_counter()-started
        if int(lengths[0]) < left+keep or len(embeddings[0]) < left+keep:
            raise ValueError('Graph produced fewer valid embeddings than requested')
        if not np.isfinite(probs).all() or not np.isfinite(embeddings).all():
            raise ValueError('Non-finite model output')
        current = probs[0, cache_len+fifo_len+left:cache_len+fifo_len+left+keep].copy()
        self.fifo = np.concatenate([self.fifo, embeddings[0, left:left+keep]])
        fifo_probs = np.concatenate([probs[0, cache_len:cache_len+fifo_len], current])
        if len(self.fifo) > self.fifo_cap:
            pop = min(max(self.update, keep+fifo_len-self.fifo_cap), len(self.fifo))
            added, added_probs = self.fifo[:pop], fifo_probs[:pop]
            silence = added_probs.sum(axis=1) < .2
            self.silence_sum += added[silence].sum(axis=0, dtype=np.float64)
            self.silence_count += int(silence.sum())
            self.cache = np.concatenate([self.cache, added])
            self.cache_probs = np.concatenate([self.cache_probs if self.compressed else probs[0, :cache_len], added_probs])
            self.fifo = self.fifo[pop:].copy()
            if len(self.cache) > 188:
                self.compress()
        if len(self.cache) > 188 or len(self.fifo) > self.fifo_cap:
            raise ValueError('Streaming state exceeds budget')
        self.steps.append(dict(mel_frames=len(features), cache_frames=cache_len, fifo_frames=fifo_len,
                               seconds=seconds, emitted_frames=keep))
        return current

    def predict(self, pcm, frontend):
        self.reset()
        # Full feature extraction is research-only and does not imply bounded PCM RAM.
        whole = mel_features(pcm) if frontend == 'whole' else None
        frame_count = len(pcm)//160
        predictions = []
        for start in range(0, frame_count, self.chunk*8):
            end = min(start+self.chunk*8, frame_count)
            left = min(8, start)
            right = min(self.right*8, frame_count-end)
            if whole is not None:
                features = whole[start-left:end+right]
            else:
                # Only arrived samples in this window are visible; flush uses real EOF.
                features = mel_features(pcm[(start-left)*160:(end+right)*160])
            prediction = self.step(np.ascontiguousarray(features), left//8, math.ceil((end-start)/8))
            predictions.append(prediction)
        return np.concatenate(predictions) if predictions else np.empty((0, 4), np.float32)


def turns_from_probs(probs, duration):
    """Fixed .5 threshold, .3s minimum speech/.5s gap, no gold tuning."""
    turns = []
    for speaker in range(4):
        active = probs[:, speaker] > .5
        edges = np.diff(np.pad(active.astype(np.int8), (1, 1)))
        spans = [(int(a)*80, min(int(b)*80, round(duration*1000))) for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]
        merged = []
        for start, end in spans:
            if merged and start-merged[-1][1] < 500:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        turns.extend(dict(start_ms=a, end_ms=b, speaker_id='slot_'+str(speaker)) for a, b in merged if b-a >= 300)
    return sorted(turns, key=lambda t: (t['start_ms'], t['end_ms'], t['speaker_id']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True)
    p.add_argument('--baseline', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--profile', choices=PROFILES, default='low')
    p.add_argument('--frontend', choices=['whole', 'window'], default='window')
    p.add_argument('--model', choices=['sortformer-streaming', 'sortformer-streaming-matmul-int8'], default='sortformer-streaming')
    args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment):
        p.error('Use exp_NNNN')
    out = ROOT / '.audio-runs' / args.experiment
    out.mkdir(parents=True, exist_ok=False)
    lock = json.loads((ROOT / 'config/audio-models.lock.json').read_text())
    descriptor = next(m for m in lock['models'] if m['id'] == args.model)
    model = next(f for f in lock['files'] if f['path'] == descriptor['files'][0])
    if sha256(ROOT / model['path']) != model['sha256']:
        raise ValueError('Changed model')
    config = dict(vars(args), model_files=[model], manifest_sha256=sha256(ROOT / args.manifest),
                  sdk_sha256=sha256(ROOT / '.build/audio/libnuclear_audio.so'),
                  ort_version=ort.__version__, threads=4, profile_frames=PROFILES[args.profile],
                  left_context_frames=1, cache_cap_frames=188, input_buffer_seconds=(PROFILES[args.profile][0]+PROFILES[args.profile][1])*.08,
                  frontend_parameters=dict(mel=128, fft=512, window=400, hop=160, hann='symmetric', dither=0, preemphasis=.97, normalization='none', log_guard=2**-24),
                  source_revision=NEMO_REV, source_url=f'https://github.com/NVIDIA-NeMo/NeMo/blob/{NEMO_REV}/nemo/collections/asr/modules/sortformer_modules.py',
                  limitations='independent NumPy frontend/state without NeMo parity; max4 slots; x86 host only; full <=180s PCM research buffer',
                  scope='experimental streaming Sortformer; preserved ASR words; no oracle; not SDK preset', input_sha256={})
    record_build(out, config)
    (out/'config.json').write_text(json.dumps(config, indent=2))
    started = time.perf_counter()
    model_runtime = Sortformer(ROOT / model['path'], args.profile)
    load_seconds = time.perf_counter()-started
    sdk = NativeSdk()
    cases = []
    for f in map(json.loads, (ROOT / args.manifest).read_text().splitlines()):
        trace_path = ROOT / '.audio-runs' / args.baseline / f['audio_id'] / 'transcript.json.trace.json'
        config['input_sha256'][str(trace_path.relative_to(ROOT))] = sha256(trace_path)
        if sha256(ROOT / f['audio']) != f['audio_sha256'] or sha256(ROOT / f['reference']) != f['reference_sha256']:
            raise ValueError('Changed frozen corpus')
        trace = json.loads(trace_path.read_text())
        pcm = sdk.decode(ROOT / f['audio'], max_frames=180*16000+16)
        if not len(pcm) or len(pcm) >= 180*16000+16:
            raise ValueError('Clip outside research budget')
        duration = len(pcm)/16000
        if f.get('audio_seconds') is not None and abs(duration-f['audio_seconds']) > .002:
            raise ValueError('Decoded duration differs')
        started = time.perf_counter()
        probs = model_runtime.predict(pcm, args.frontend)
        wall_seconds = time.perf_counter()-started
        turns = turns_from_probs(probs, duration)
        predicted = attribute(trace['words'], turns)
        if normalize(' '.join(t['text'] for t in predicted)) != normalize(' '.join(w['text'] for w in trace['words'])):
            raise ValueError('Speaker processing changed words')
        truth = json.loads((ROOT / f['reference']).read_text())['transcript']
        case = dict(audio_id=f['audio_id'], audio_seconds=duration, wall_seconds=wall_seconds,
                    inference_rtf=wall_seconds/duration, model_seconds=sum(t['seconds'] for t in model_runtime.steps),
                    process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    speaker_attributed=cpwer(truth, predicted), **speaker_coverage(predicted),
                    calls=len(model_runtime.steps), max_call_seconds=max(t['seconds'] for t in model_runtime.steps))
        if f.get('rttm'):
            case.update(diarization(truth, turns, duration))
        (out/(f['audio_id']+'.trace.json')).write_text(json.dumps(dict(turns=turns, utterances=predicted, steps=model_runtime.steps), indent=2))
        np.save(out/(f['audio_id']+'.probs.npy'), probs)
        cases.append(case)
        print(json.dumps(case), flush=True)
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], load_seconds=load_seconds, cases=cases,
                   cpwer=sum(c['speaker_attributed']['errors'] for c in cases)/sum(c['speaker_attributed']['reference_words'] for c in cases),
                   inference_rtf=sum(c['wall_seconds'] for c in cases)/sum(c['audio_seconds'] for c in cases),
                   process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    report = ROOT / 'eval/results' / args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2))
        (report/name).write_bytes((out/name).read_bytes())


if __name__ == '__main__':
    main()
