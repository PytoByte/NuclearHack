#!/usr/bin/env python3
"""Bounded-window CPU diarization research; preserved ASR, model-declared slot cap.

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
import subprocess
from pathlib import Path
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
TRANSFORMERS_REV = '0f53828e83f2212060233d2ea552cc76617b8712'
PROFILES = {'low': (6, 7, 188, 144), 'buffered': (340, 40, 40, 300)}
V3_PROFILES = {'low': (9, 4, 264, 222), 'buffered': (340, 40, 40, 300)}


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
    # Torch builds Hann with float32 arange/multiply/cos, rather than float64 hanning.
    phase = np.arange(400, dtype=np.float32)*np.float32(2*np.pi/399)
    window = np.pad(np.float32(.5)-np.float32(.5)*np.cos(phase), (56, 56))
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
    # librosa casts triangular ramps before applying Slaney's float64 normalization.
    filters = np.maximum(0, np.minimum(lower, upper)).astype(np.float32)
    filters *= (2/(hz[2:]-hz[:-2]))[:, None]
    features = np.log(power @ filters.T + np.float32(2**-24))
    # NeMo's reported valid length excludes the extra centered frame.
    return np.ascontiguousarray(features[:len(pcm)//160], dtype=np.float32)


class Sortformer:
    speakers = 4
    cache_cap = 188
    silence_frames = 3
    fixed_silence = None
    left_context = 1
    hires = False

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
        self.cache_probs = np.empty((0, self.speakers), np.float32)
        self.compressed = False
        self.silence_sum = np.zeros(512, np.float64)
        self.silence_count = 0
        self.steps = []

    def compress(self):
        probs = self.cache_probs
        log_p = np.log(np.maximum(probs, .25))
        log_q = np.log(np.maximum(1-probs, .25))
        scores = log_p-log_q+log_q.sum(axis=1, keepdims=True)-np.log(.5)
        per_speaker = self.cache_cap//self.speakers-self.silence_frames
        positive = ((scores > 0) & (probs > .5)).sum(axis=0)
        scores[(probs <= .5) | ((scores <= 0) & (positive >= math.floor(per_speaker*.5))[None, :])] = -np.inf
        scores[self.cache_cap:] += .05
        for count, boost in [(math.floor(per_speaker*.75), 2), (math.floor(per_speaker*1.5), 1)]:
            for speaker in range(self.speakers):
                indices = np.argsort(-scores[:, speaker], kind='stable')[:count]
                scores[indices, speaker] -= boost*np.log(.5)
        scores = np.concatenate([scores, np.full((self.silence_frames, self.speakers), np.inf, np.float32)])
        flat = scores.T.reshape(-1)
        chosen = np.argsort(-flat, kind='stable')[:self.cache_cap]
        chosen[np.isneginf(flat[chosen])] = 99999
        chosen.sort()
        frames = chosen % len(scores)
        disabled = (chosen == 99999) | (frames >= len(self.cache))
        frames[disabled] = 0
        self.cache = self.cache[frames].copy()
        self.cache_probs = probs[frames].copy()
        silence = self.fixed_silence if self.fixed_silence is not None else self.silence_sum/max(1, self.silence_count)
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
            if len(self.cache) > self.cache_cap:
                self.compress()
        if len(self.cache) > self.cache_cap or len(self.fifo) > self.fifo_cap:
            raise ValueError('Streaming state exceeds budget')
        self.steps.append(dict(mel_frames=len(features), cache_frames=cache_len, fifo_frames=fifo_len,
                               seconds=seconds, emitted_frames=keep))
        return current

    def predict(self, pcm, frontend, reference_features=None):
        self.reset()
        # Full feature extraction is research-only and does not imply bounded PCM RAM.
        whole = reference_features if reference_features is not None else mel_features(pcm) if frontend == 'whole' else None
        frame_count = len(pcm)//160
        predictions = []
        for start in range(0, frame_count, self.chunk*8):
            end = min(start+self.chunk*8, frame_count)
            left = min(self.left_context*8, start)
            right = min(self.right*8, frame_count-end)
            if whole is not None:
                features = whole[start-left:end+right]
            else:
                # Only arrived samples in this window are visible; flush uses real EOF.
                features = mel_features(pcm[(start-left)*160:(end+right)*160])
            prediction = self.step(np.ascontiguousarray(features), left//8, math.ceil((end-start)/8))
            predictions.append(prediction)
        output = np.concatenate(predictions) if predictions else np.empty((0, self.speakers), np.float32)
        return output[:frame_count] if self.hires else output


class Nemotron3(Sortformer):
    """Transformers ONNX graph, 10ms logits, learned silence and bounded eight-slot cache.

    Cache policy follows Nemotron3DiarizationSpeakerCache at Transformers
    0f53828e83f2212060233d2ea552cc76617b8712; NumPy stable tie ordering is explicit.
    """
    speakers = 8
    cache_cap = 264
    silence_frames = 1
    left_context = 0
    hires = True

    def __init__(self, model, profile):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), options, providers=['CPUExecutionProvider'])
        self.chunk, self.right, self.fifo_cap, self.update = V3_PROFILES[profile]
        self.reset()

    def step(self, features, left, keep):
        from scipy.special import expit
        cache_len, fifo_len = len(self.cache), len(self.fifo)
        cached = np.concatenate([self.cache, self.fifo])[None]
        frames = math.ceil(len(features)/8)
        inputs = dict(input_features=features[None], cached_embeds=cached,
                      attention_mask=np.ones((1, cache_len+fifo_len+frames), np.int64))
        started = time.perf_counter()
        logits, embeddings, silence = self.session.run(None, inputs)
        seconds = time.perf_counter()-started
        total = cache_len+fifo_len+frames
        if logits.shape != (1, total*8, 8) or embeddings.shape != (1, frames, 512) or silence.shape != (512,):
            raise ValueError('Unexpected Nemotron3 output grid')
        if not all(np.isfinite(v).all() for v in [logits, embeddings, silence]):
            raise ValueError('Non-finite Nemotron3 output')
        if self.fixed_silence is not None and not np.array_equal(self.fixed_silence, silence):
            raise ValueError('Learned silence embedding unexpectedly changed')
        self.fixed_silence = silence.copy()
        hires = expit(logits[0])
        probs = hires.reshape(total, 8, 8).mean(axis=1)
        offset = cache_len+fifo_len+left
        current = probs[offset:offset+keep]
        self.fifo = np.concatenate([self.fifo, embeddings[0, left:left+keep]])
        fifo_probs = np.concatenate([probs[cache_len:cache_len+fifo_len], current])
        if len(self.fifo) > self.fifo_cap:
            pop = min(max(self.update, keep+fifo_len-self.fifo_cap), len(self.fifo))
            self.cache = np.concatenate([self.cache, self.fifo[:pop]])
            self.cache_probs = np.concatenate([self.cache_probs if self.compressed else probs[:cache_len], fifo_probs[:pop]])
            self.fifo = self.fifo[pop:].copy()
            if len(self.cache) > self.cache_cap:
                self.compress()
        if len(self.cache) > self.cache_cap or len(self.fifo) > self.fifo_cap:
            raise ValueError('Nemotron3 streaming state exceeds budget')
        self.steps.append(dict(mel_frames=len(features), cache_frames=cache_len, fifo_frames=fifo_len,
                               seconds=seconds, emitted_frames=keep, output_resolution_ms=10))
        return hires[offset*8:(offset+keep)*8].copy()


def turns_from_probs(probs, duration, resolution_ms=80):
    """Fixed .5 threshold, .3s minimum speech/.5s gap, no gold tuning."""
    turns = []
    for speaker in range(probs.shape[1]):
        active = probs[:, speaker] > .5
        edges = np.diff(np.pad(active.astype(np.int8), (1, 1)))
        spans = [(int(a)*resolution_ms, min(int(b)*resolution_ms, round(duration*1000))) for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]
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
    p.add_argument('--model', choices=['sortformer-streaming', 'sortformer-streaming-matmul-int8', 'nemotron3-diarization-q8'], default='sortformer-streaming')
    p.add_argument('--reference-frontend', action='store_true', help='Diagnostic Torch/librosa frontend in a separate child; buffered whole mode only')
    args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment):
        p.error('Use exp_NNNN')
    if args.reference_frontend and (args.profile != 'buffered' or args.frontend != 'whole'):
        p.error('Reference frontend diagnostic requires buffered/whole mode')
    out = ROOT / '.audio-runs' / args.experiment
    out.mkdir(parents=True, exist_ok=False)
    lock = json.loads((ROOT / 'config/audio-models.lock.json').read_text())
    descriptor = next(m for m in lock['models'] if m['id'] == args.model)
    files = [next(f for f in lock['files'] if f['path'] == path) for path in descriptor['files']]
    model = files[0]
    for item in files:
        if sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError('Changed model asset: '+item['path'])
    v3 = args.model == 'nemotron3-diarization-q8'
    profile = (V3_PROFILES if v3 else PROFILES)[args.profile]
    resolution_ms = 10 if v3 else 80
    config = dict(vars(args), model_files=files, manifest_sha256=sha256(ROOT / args.manifest),
                  sdk_sha256=sha256(ROOT / '.build/audio/libnuclear_audio.so'),
                  ort_version=ort.__version__, threads=4, profile_frames=profile,
                  left_context_frames=0 if v3 else 1, cache_cap_frames=264 if v3 else 188, output_resolution_ms=resolution_ms,
                  input_buffer_seconds=(profile[0]+profile[1])*.08,
                  frontend_parameters=dict(mel=128, fft=512, window=400, hop=160, hann='symmetric', dither=0, preemphasis=.97, normalization='none', log_guard=2**-24),
                  source_revision=TRANSFORMERS_REV if v3 else NEMO_REV,
                  source_url=f'https://github.com/huggingface/transformers/blob/{TRANSFORMERS_REV}/src/transformers/models/nemotron3_diarization/modeling_nemotron3_diarization.py' if v3 else f'https://github.com/NVIDIA-NeMo/NeMo/blob/{NEMO_REV}/nemo/collections/asr/modules/sortformer_modules.py',
                  limitations=f'independent NumPy frontend/state without full reference parity; max{8 if v3 else 4} slots; x86 host only; full <=180s PCM research buffer',
                  reference_frontend_memory='child Torch/librosa RSS excluded from parent peak; not a deployment profile' if args.reference_frontend else None,
                  scope='experimental streaming Sortformer; preserved ASR words; no oracle; not SDK preset', input_sha256={})
    record_build(out, config)
    (out/'config.json').write_text(json.dumps(config, indent=2))
    started = time.perf_counter()
    model_runtime = (Nemotron3 if v3 else Sortformer)(ROOT / model['path'], args.profile)
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
        reference_features = None
        reference_frontend_seconds = None
        if args.reference_frontend:
            reference_started = time.perf_counter()
            source = out/(f['audio_id']+'.pcm.npz')
            target = out/(f['audio_id']+'.reference-features.npz')
            np.savez(source, pcm=pcm)
            subprocess.run([str(ROOT/'.tools/frontend-env/bin/python'), str(ROOT/'eval/scripts/probe_frontend_conformance.py'),
                            '--reference', str(source), str(target)], check=True)
            with np.load(target) as features:
                reference_features = features['pcm'].copy()
            if reference_features.shape != (len(pcm)//160, 128):
                raise ValueError('Reference frontend shape differs')
            reference_frontend_seconds = time.perf_counter()-reference_started
            config['input_sha256'][str(target.relative_to(ROOT))] = sha256(target)
            config['reference_versions'] = json.loads(Path(str(target)+'.versions.json').read_text())
        started = time.perf_counter()
        probs = model_runtime.predict(pcm, args.frontend, reference_features)
        wall_seconds = time.perf_counter()-started
        turns = turns_from_probs(probs, duration, resolution_ms=resolution_ms)
        predicted = attribute(trace['words'], turns)
        if normalize(' '.join(t['text'] for t in predicted)) != normalize(' '.join(w['text'] for w in trace['words'])):
            raise ValueError('Speaker processing changed words')
        truth = json.loads((ROOT / f['reference']).read_text())['transcript']
        case = dict(audio_id=f['audio_id'], audio_seconds=duration, wall_seconds=wall_seconds,
                    inference_rtf=wall_seconds/duration, model_seconds=sum(t['seconds'] for t in model_runtime.steps),
                    process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    speaker_attributed=cpwer(truth, predicted), **speaker_coverage(predicted),
                    calls=len(model_runtime.steps), max_call_seconds=max(t['seconds'] for t in model_runtime.steps))
        if args.reference_frontend:
            case['reference_frontend_seconds_excluded_from_inference_rtf'] = reference_frontend_seconds
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
