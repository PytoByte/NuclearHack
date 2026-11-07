#!/usr/bin/env python3
"""Isolate official pipeline's 160ms posterior anchor using frozen GigaAM words.

No new inference or oracle count. The posterior field and ASR are unchanged;
only word-to-speaker assignment changes. Fixed policy from NeMo-Speech.cpp
v0.3.0 sortformer_model.h / diar_pipeline.cpp, not tuned to these references.
"""
import argparse
import json
import re
import sys
import numpy as np
from native_sdk import ROOT, record_harness
from scoring import normalize, speaker_coverage
from probe_sortformer import turns_from_probs
from probe_attribution import attribute
from run_file_pipeline import cpwer
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256

SOURCES = [
    ('eval/data/russian-conversation-pilot.jsonl', 'exp_0099', 'exp_0166'),
    ('eval/data/russian-conversation-heldout-session.jsonl', 'exp_0104', 'exp_0169'),
    ('eval/data/russian-conversation-movie-session.jsonl', 'exp_0101', 'exp_0170'),
    ('eval/data/russian-conversation-astrology-session.jsonl', 'exp_0155', 'exp_0171'),
]


def posterior_words(words, probabilities, anchor_ms):
    if probabilities.ndim != 2 or probabilities.shape[1] != 8 or not len(probabilities):
        raise ValueError('Expected nonempty 10ms/8slot posteriors')
    if not np.isfinite(probabilities).all() or probabilities.min() < 0 or probabilities.max() > 1:
        raise ValueError('Invalid probability values')
    rows = []
    for w in words:
        start = int(w['start_ms']//10)
        end = int(np.ceil(w['end_ms']/10))
        start = min(max(start, 0), len(probabilities)-1)
        end = max(start+1, min(end, len(probabilities)))
        if anchor_ms: end = min(end, start+anchor_ms//10)
        speaker = int(probabilities[start:end].mean(axis=0, dtype=np.float64).argmax())
        rows.append(dict(speaker_id='slot_'+str(speaker), start_ms=w['start_ms'], end_ms=w['end_ms'], text=w['text']))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--experiment', required=True); args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment): p.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment; out.mkdir(parents=True, exist_ok=False)
    config = dict(vars(args), source_revision='20999cc921d2b14aa58708f61756a8b2e787ba20',
        source_url='https://github.com/NVIDIA/NeMo-Speech.cpp/blob/v0.3.0/src/asr/diar/diar_pipeline.cpp',
        scope='model-free pipeline attribution comparison; six known silver files; same ASR/times/posteriors, not independent gold',
        variants=['threshold_turn_overlap', 'posterior_whole_word', 'posterior_first_160ms'], input_sha256={})
    record_harness(out, config)
    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
        return json.loads(path.read_text())
    cases = []
    for manifest, baseline, posterior_run in SOURCES:
        entries = [json.loads(line) for line in (ROOT/manifest).read_text().splitlines()]
        config['input_sha256'][manifest] = sha256(ROOT/manifest)
        previous = {c['audio_id']: c for c in read(ROOT/'.audio-runs'/posterior_run/'metrics.json')['cases']}
        for f in entries:
            ident = f['audio_id']
            reference = ROOT/f['reference']
            if sha256(reference) != f['reference_sha256']: raise ValueError('Changed reference')
            truth = read(reference)['transcript']
            words = read(ROOT/'.audio-runs'/baseline/ident/'transcript.json.trace.json')['words']
            path = ROOT/'.audio-runs'/posterior_run/(ident+'.probs.npy')
            config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
            probs = np.load(path)
            if abs(len(probs)*.01-f['audio_seconds']) > .02: raise ValueError('Wrong source posterior duration')
            variants = dict(threshold_turn_overlap=attribute(words, turns_from_probs(probs, f['audio_seconds'], resolution_ms=10)),
                posterior_whole_word=posterior_words(words, probs, 0), posterior_first_160ms=posterior_words(words, probs, 160))
            expected = normalize(' '.join(w['text'] for w in words))
            for rows in variants.values():
                if normalize(' '.join(w['text'] for w in rows)) != expected: raise ValueError('ASR text changed')
            scores = {k: dict(speaker_attributed=cpwer(truth, rows), **speaker_coverage(rows)) for k, rows in variants.items()}
            if scores['threshold_turn_overlap']['speaker_attributed'] != previous[ident]['speaker_attributed']:
                raise ValueError('Baseline attribution not reproduced')
            cases.append(dict(audio_id=ident, baseline=posterior_run, variants=scores))
            (out/(ident+'.variants.json')).write_text(json.dumps(variants, indent=2))
    combined = {}
    for name in config['variants']:
        values = [c['variants'][name]['speaker_attributed'] for c in cases]
        errors = sum(s['errors'] for s in values); total = sum(s['reference_words'] for s in values)
        combined[name] = dict(errors=errors, reference_words=total, cpwer=errors/total)
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases, variants=combined,
                   der_unchanged=True, note='posterior field unchanged; direct argmax always assigns a slot, including low-confidence spans')
    report = ROOT/'eval/results'/args.experiment; report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2)); (report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(combined), flush=True)


if __name__ == '__main__': main()
