#!/usr/bin/env python3
"""Independent character CTC alignment; freeze GigaAM words and speaker field.

20s source chunks exactly match original ASR. Unsupported words cause whole
chunk timing fallback; text is never normalized/replaced in the output.
"""
import argparse
import json
import re
import resource
import sys
import time
import unicodedata
import numpy as np
import onnxruntime as ort
from ctc_alignment import align_tokens
from native_sdk import ROOT, NativeSdk, record_build
from probe_posterior_attribution import SOURCES, posterior_words
from run_file_pipeline import cpwer
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment): parser.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment; out.mkdir(parents=True, exist_ok=False)
    lock = json.loads((ROOT/'config/audio-models.lock.json').read_text())
    model = next(m for m in lock['models'] if m['id'] == 'russian-aligner-wav2vec2-q8')
    files = [f for f in lock['files'] if f['path'] in model['files']]
    for f in files:
        if sha256(ROOT/f['path']) != f['sha256']: raise ValueError('Changed pinned aligner')
    config = dict(vars(args), model_files=files, sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),
        threads=4, input_sha256={}, scope='six known RU silver records; independent ONNX char CTC alignment; fixed ASR text/posteriors, no timestamp ground truth',
        policy='original ASR chunks <=20s; per-chunk zero-mean unit-variance; standard complete CTC Viterbi; frame grid stride320/receptive400; unsupported/infeasible chunk keeps original times; first160ms speaker posterior anchor',
        upstream='https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py',
        source_revision='df5ba1d9e0f9a34c44eec437b441f4ae43c842eb')
    record_build(out, config)
    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
        return json.loads(path.read_text())
    options = ort.SessionOptions(); options.intra_op_num_threads = 4; options.inter_op_num_threads = 1
    began = time.perf_counter()
    session = ort.InferenceSession(str(ROOT/'models/russian-aligner/model_quantized.onnx'), options, providers=['CPUExecutionProvider'])
    load = time.perf_counter()-began
    vocab = json.loads((ROOT/'models/russian-aligner/vocab.json').read_text())
    sdk = NativeSdk(); cases = []
    (out/'config.json').write_text(json.dumps(config, indent=2))
    for manifest, baseline, posterior_run in SOURCES:
        for entry in map(json.loads, (ROOT/manifest).read_text().splitlines()):
            ident = entry['audio_id']
            for key in ['audio', 'reference']:
                if sha256(ROOT/entry[key]) != entry[key+'_sha256']: raise ValueError('Changed fixture')
            trace = read(ROOT/'.audio-runs'/baseline/ident/'transcript.json.trace.json')
            words = trace['words']; aligned = [dict(w) for w in words]
            pcm = sdk.decode(ROOT/entry['audio'], max_frames=180*16000+16)
            if len(pcm) >= 180*16000+16: raise ValueError('Exceeds research budget')
            raw_path = ROOT/'.audio-runs'/posterior_run/(ident+'.probs.npy')
            config['input_sha256'][str(raw_path.relative_to(ROOT))] = sha256(raw_path)
            probs = np.load(raw_path)
            chunks = []; began = time.perf_counter()
            for chunk in trace['asr']:
                offset, size = chunk['offset_frames'], chunk['frames']
                indices = [i for i,w in enumerate(words) if offset*1000/16000 <= w['start_ms'] < (offset+size)*1000/16000]
                if not indices: continue
                tokens, owners = [], []
                unsupported = []
                for index in indices:
                    text = unicodedata.normalize('NFC', words[index]['text']).lower()
                    if not text or any(c not in vocab or c in '<>|' for c in text):
                        unsupported.append(index)
                    if tokens: tokens.append(vocab['|']); owners.append(None)
                    for c in text:
                        tokens.append(vocab.get(c, vocab['<unk>'])); owners.append(index)
                if unsupported:
                    chunks.append(dict(offset=offset, frames=size, fallback='unsupported word', unsupported_count=len(unsupported)))
                    continue
                source = pcm[offset:offset+size]
                source = ((source-source.mean())/np.sqrt(source.var()+1e-7)).astype(np.float32)
                inference_start = time.perf_counter()
                logits = session.run(None, {'input_values':source[None]})[0][0]
                inference = time.perf_counter()-inference_start
                if len(logits) != (size-400)//320+1: raise ValueError('Unexpected CTC source grid')
                logits = logits.astype(np.float64)
                logits -= logits.max(axis=1, keepdims=True)
                logits -= np.log(np.exp(logits).sum(axis=1, keepdims=True))
                try:
                    spans, score = align_tokens(logits, tokens)
                except ValueError as error:
                    chunks.append(dict(offset=offset, frames=size, fallback=str(error)))
                    continue
                for index in indices:
                    owned = [span for owner,span in zip(owners,spans) if owner == index]
                    start = offset+owned[0][0]*320
                    end = min(offset+size, offset+(owned[-1][1]-1)*320+400)
                    aligned[index]['start_ms'] = start*1000/16000
                    aligned[index]['end_ms'] = end*1000/16000
                chunks.append(dict(offset=offset, frames=size, alignment_score=score,
                    inference_seconds=inference, aligned_words=len(indices)))
                print(json.dumps(dict(audio_id=ident, offset=offset, inference_seconds=inference)), flush=True)
            elapsed = time.perf_counter()-began
            if [w['text'] for w in aligned] != [w['text'] for w in words]: raise ValueError('ASR lexical mutation')
            if any(not 0 <= w['start_ms'] < w['end_ms'] <= len(pcm)*1000/16000+.001 for w in aligned): raise ValueError('Invalid word source grid')
            truth = read(ROOT/entry['reference'])['transcript']
            variants = {name:cpwer(truth, posterior_words(value, probs, 160)) for name,value in [('original_timing', words), ('independent_ctc_timing', aligned)]}
            changes = [abs(a['start_ms']-b['start_ms']) for a,b in zip(words,aligned)]
            cases.append(dict(audio_id=ident, variants=variants, processing_seconds=elapsed,
                rtf=elapsed/(len(pcm)/16000), chunks=chunks, words=len(words), lexical_text_identical=True,
                aligned_words=sum(c.get('aligned_words',0) for c in chunks), median_start_shift_ms=float(np.median(changes))))
            (out/(ident+'.words.json')).write_text(json.dumps(aligned, indent=2))
            print(json.dumps(dict(audio_id=ident, scores=variants)), flush=True)
    combined = {}
    for name in ['original_timing','independent_ctc_timing']:
        scores = [c['variants'][name] for c in cases]
        errors = sum(s['errors'] for s in scores); total = sum(s['reference_words'] for s in scores)
        combined[name] = dict(errors=errors, reference_words=total, cpwer=errors/total)
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], variants=combined, cases=cases,
        load_seconds=load, process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        python_ort_version=ort.__version__, diarization_field_unchanged=True,
        limitation='No manual word timestamps; shifts are diagnostic, not MAE. Fixed GigaAM errors may force implausible alignments. Host memory includes SDK decode and Python, not target RAM.')
    report = ROOT/'eval/results'/args.experiment; report.mkdir(parents=True, exist_ok=False)
    for name, value in [('config.json',config),('metrics.json',metrics)]:
        (out/name).write_text(json.dumps(value, indent=2)); (report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(combined), flush=True)


if __name__ == '__main__': main()
