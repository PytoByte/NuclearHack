#!/usr/bin/env python3
"""Paired recording-level comparison of Sortformer probes and native refinement."""
import argparse
import json
import re
import sys
import numpy as np
from native_sdk import ROOT, record_harness
from probe_reclustering import diarization
from probe_attribution import attribute
from run_file_pipeline import cpwer
from scoring import normalize, text_metrics, aggregate
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256


def summary(cases):
    words = sum(c['speaker_attributed']['reference_words'] for c in cases)
    seconds = sum(c['der_details']['total'] for c in cases)
    speakers = sum(c['reference_speakers'] for c in cases)
    return dict(cpwer=sum(c['speaker_attributed']['errors'] for c in cases)/words,
                der=sum(sum(c['der_details'][k] for k in ['confusion', 'false alarm', 'missed detection']) for c in cases)/seconds,
                jer=sum(c['jer']*c['reference_speakers'] for c in cases)/speakers)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True)
    p.add_argument('--baseline', default='exp_0099')
    p.add_argument('--candidates', nargs='+', required=True)
    p.add_argument('--manifest', default='eval/data/russian-conversation-pilot.jsonl')
    p.add_argument('--frontend-pair', nargs=2)
    p.add_argument('--comparison-baseline', help='Optional listed candidate for paired deltas; native baseline still supplies fixed ASR words')
    args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment):
        p.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment
    out.mkdir(parents=True, exist_ok=False)
    config = dict(vars(args), manifest_sha256=sha256(ROOT/args.manifest), seed=42, bootstrap_samples=10000,
                  collar_seconds=.25, skip_overlap=False, input_sha256={},
                  scope='paired source-file silver comparison; speaker independence unverified, not gold/ARM validation')
    record_harness(out, config)

    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
        return json.loads(path.read_text())

    cases = {run: [] for run in [args.baseline, *args.candidates]}
    lexical = []
    for f in map(json.loads, (ROOT/args.manifest).read_text().splitlines()):
        if not f.get('rttm'):
            raise ValueError('Only conversational RTTM cases; source occupancy not accepted as speech GT')
        reference = ROOT/f['reference']
        if sha256(reference) != f['reference_sha256']:
            raise ValueError('Changed reference')
        truth = read(reference)['transcript']
        trace = read(ROOT/'.audio-runs'/args.baseline/f['audio_id']/'transcript.json.trace.json')
        words = trace['words']
        baseline = [dict(start_ms=t['start_ms'], end_ms=t['end_ms'], speaker_id=str(t['speaker'])) for t in trace['speaker_turns']]
        refs = ' '.join(t['text'] for t in truth)
        raw_words = ' '.join(w['text'] for w in words)
        lexical.append(dict(audio_id=f['audio_id'], text_metrics=text_metrics(refs, raw_words)))
        for run in cases:
            if run == args.baseline:
                turns = baseline
            else:
                candidate = read(ROOT/'.audio-runs'/run/(f['audio_id']+'.trace.json'))
                turns = candidate['turns']
                actual = candidate['utterances']
                if normalize(' '.join(t['text'] for t in actual)) != normalize(raw_words):
                    raise ValueError('Candidate lexical sequence differs')
                # Labels can differ; attribution and words must reproduce the captured output.
                if attribute(words, turns) != actual:
                    raise ValueError('Candidate uses different words/timestamps or attribution')
            predicted = attribute(words, turns)
            cases[run].append(dict(audio_id=f['audio_id'], speaker_attributed=cpwer(truth, predicted),
                                   reference_speakers=len({t['speaker_id'] for t in truth}),
                                   **diarization(truth, turns, f['audio_seconds'])))
    results = {run: dict(**summary(rows), cases=rows) for run, rows in cases.items()}
    comparison_baseline = args.comparison_baseline or args.baseline
    if comparison_baseline not in cases:
        p.error('Comparison baseline must be present in --baseline/--candidates')
    n = len(lexical)
    indices = np.random.default_rng(42).integers(0, n, (10000, n))
    for run in args.candidates:
        differences = {key: [] for key in ['cpwer', 'der', 'jer']}
        for sample in indices:
            a = summary([cases[comparison_baseline][i] for i in sample])
            b = summary([cases[run][i] for i in sample])
            for key in differences:
                differences[key].append(b[key]-a[key])
        results[run]['paired_recording_bootstrap_delta_ci95'] = {k: np.quantile(v, [.025, .975]).tolist() for k, v in differences.items()}
    frontend_control = []
    if args.frontend_pair:
        a_run, b_run = args.frontend_pair
        a_config = read(ROOT/'.audio-runs'/a_run/'config.json')
        b_config = read(ROOT/'.audio-runs'/b_run/'config.json')
        for key in ['baseline', 'manifest', 'model_files', 'profile', 'profile_frames']:
            if a_config[key] != b_config[key]:
                raise ValueError('Frontend control changes another factor: '+key)
        for path in sorted((ROOT/'.audio-runs'/a_run).glob('*.probs.npy')):
            other = ROOT/'.audio-runs'/b_run/path.name
            for source in [path, other]:
                config['input_sha256'][str(source.relative_to(ROOT))] = sha256(source)
            a, b = np.load(path), np.load(other)
            if a.shape != b.shape:
                raise ValueError('Frontend frame grids differ')
            frontend_control.append(dict(audio_id=path.name.removesuffix('.probs.npy'), frames=len(a),
                                         max_posterior_delta=float(np.max(abs(a-b))),
                                         threshold_decision_flips=int(((a>.5)!=(b>.5)).sum())))
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], recordings=n, runs=results,
                   comparison_baseline=comparison_baseline,
                   normalized=aggregate([c['text_metrics']['normalized'] for c in lexical]),
                   lexical_invariance_verified=True, lexical_cases=lexical,
                   frontend_control=frontend_control,
                   limitation='small reused dev/source-file corpus; exploratory intervals do not establish people-disjoint generalization')
    report = ROOT/'eval/results'/args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2))
        (report/name).write_bytes((out/name).read_bytes())
    print(json.dumps({run: {k: v for k, v in result.items() if k != 'cases'} for run, result in results.items()}, indent=2))


if __name__ == '__main__':
    main()
