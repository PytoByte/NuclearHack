#!/usr/bin/env python3
"""Pair the complete official pipeline against frozen GigaAM/ONNX-Q8 cases."""
import argparse
import json
import re
import sys
import numpy as np
from native_sdk import ROOT, record_harness
from scoring import counts
from probe_posterior_attribution import SOURCES
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--experiment', required=True); args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment): p.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment; out.mkdir(parents=True, exist_ok=False)
    config = dict(vars(args), inputs=['exp_0189', 'exp_0190', 'exp_0191', 'exp_0192', 'exp_0193'],
        seed=42, bootstrap_samples=10000, input_sha256={},
        scope='six known silver source files, complete native pipeline vs frozen GigaAM/ONNX-Q8; not blind gold or ARM')
    record_harness(out, config)
    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
        return json.loads(path.read_text())
    cases = []
    lexical = {}
    for manifest, baseline, _ in SOURCES:
        config['input_sha256'][manifest] = sha256(ROOT/manifest)
        for f in map(json.loads, (ROOT/manifest).read_text().splitlines()):
            reference = ROOT/f['reference']
            if sha256(reference) != f['reference_sha256']: raise ValueError('Changed source reference')
            truth = read(reference)['transcript']
            words = read(ROOT/'.audio-runs'/baseline/f['audio_id']/'transcript.json.trace.json')['words']
            lexical[f['audio_id']] = counts(' '.join(w['text'] for w in truth), ' '.join(w['text'] for w in words))
    attrib = {c['audio_id']: c for c in read(ROOT/'eval/results/exp_0190/metrics.json')['cases']}
    actual = {}
    for run in ['exp_0189', 'exp_0191', 'exp_0192', 'exp_0193']:
        current = read(ROOT/'eval/results'/run/'config.json')
        if actual:
            for field in ['runtime', 'model_files', 'threads', 'language', 'diarization_preset', 'stream', 'diarize']:
                if current[field] != previous[field]: raise ValueError('Pipeline comparison changes '+field)
        previous = current
        for c in read(ROOT/'eval/results'/run/'metrics.json')['cases']:
            if c['audio_id'] in actual: raise ValueError('Duplicate source case')
            actual[c['audio_id']] = c
    if set(actual) != set(attrib): raise ValueError('Different case sets')
    totals = {k: 0 for k in ['reference_words', 'giga_wer_errors', 'nemo_wer_errors', 'nemo_cpwer_errors', 'giga_q8_cpwer_errors', 'giga_q8_anchor_errors']}
    for ident, c in actual.items():
        norm = c['text_metrics']['normalized']
        variants = attrib[ident]['variants']
        cp = c['speaker_attributed']
        if norm['reference_words'] != cp['reference_words']: raise ValueError('WER/cpWER reference denominator differs')
        if cp['reference_words'] != variants['threshold_turn_overlap']['speaker_attributed']['reference_words']:
            raise ValueError('Source reference denominator differs')
        if lexical[ident]['reference_words'] != norm['reference_words']: raise ValueError('Lexical reference differs')
        row = dict(audio_id=ident, reference_words=cp['reference_words'],
                   giga_wer_errors=sum(lexical[ident][k] for k in ['substitutions', 'deletions', 'insertions']),
                   nemo_wer_errors=sum(norm[k] for k in ['substitutions', 'deletions', 'insertions']),
                   nemo_cpwer_errors=cp['errors'],
                   giga_q8_cpwer_errors=variants['threshold_turn_overlap']['speaker_attributed']['errors'],
                   giga_q8_anchor_errors=variants['posterior_first_160ms']['speaker_attributed']['errors'],
                   nemo_full_rtf=c['full_rtf'], nemo_sampled_pss_kib=c['sampled_peak_pss_kib'])
        for key in totals: totals[key] += row[key]
        cases.append(row)
    paired = {}
    rng = np.random.default_rng(config['seed'])
    indices = rng.integers(0, len(cases), size=(config['bootstrap_samples'], len(cases)))
    weights = np.array([c['reference_words'] for c in cases])
    candidate = np.array([c['nemo_cpwer_errors'] for c in cases])
    for baseline in ['giga_q8_cpwer_errors', 'giga_q8_anchor_errors']:
        errors = np.array([c[baseline] for c in cases])
        delta = (candidate[indices]-errors[indices]).sum(axis=1)/weights[indices].sum(axis=1)
        paired[baseline] = dict(delta_cpwer=(candidate.sum()-errors.sum())/weights.sum(),
            record_bootstrap_ci95=list(map(float, np.quantile(delta, [.025, .975]))), lower_is_better=True)
    total_words = totals['reference_words']
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases, counts=totals,
        giga_normalized_wer=totals['giga_wer_errors']/total_words, nemo_normalized_wer=totals['nemo_wer_errors']/total_words, nemo_cpwer=totals['nemo_cpwer_errors']/total_words,
        giga_q8_cpwer=totals['giga_q8_cpwer_errors']/total_words, giga_q8_anchor_cpwer=totals['giga_q8_anchor_errors']/total_words,
        paired=paired, limitation='Known small silver corpus; record bootstrap cannot establish people-disjoint generalization. Timings unpaired; do not infer causal speedup.')
    report = ROOT/'eval/results'/args.experiment; report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2)); (report/name).write_bytes((out/name).read_bytes())
    print(json.dumps({k: v for k, v in metrics.items() if k != 'cases'}), flush=True)


if __name__ == '__main__': main()
