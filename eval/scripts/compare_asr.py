#!/usr/bin/env python3
"""Paired screening comparisons; resample source sentence groups, not words."""
import argparse
import json
import hashlib
from pathlib import Path
import re

import jiwer
import numpy as np
from native_sdk import ROOT
from scoring import aggregate, normalize, counts


def paired_interval(a, b, groups, iterations=10000):
    unique = sorted(set(groups))
    errors_a, errors_b, words = [], [], []
    for group in unique:
        indices = [i for i, label in enumerate(groups) if label == group]
        errors_a.append(sum(sum(a[i]['normalized'][k] for k in ('substitutions', 'deletions', 'insertions')) for i in indices))
        errors_b.append(sum(sum(b[i]['normalized'][k] for k in ('substitutions', 'deletions', 'insertions')) for i in indices))
        words.append(sum(a[i]['normalized']['reference_words'] for i in indices))
    choice = np.random.default_rng(42).integers(0, len(unique), (iterations, len(unique)))
    delta = (np.asarray(errors_b)[choice].sum(1) - np.asarray(errors_a)[choice].sum(1)) / np.asarray(words)[choice].sum(1)
    return dict(delta_wer_b_minus_a_95ci=np.quantile(delta, [0.025, 0.975]).tolist(),
                source_sentence_groups=len(unique), resamples=iterations, seed=42)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiments', nargs='+')
    parser.add_argument('--output',type=Path,default=ROOT/'eval/results/asr-comparison.json')
    args = parser.parse_args()
    report = dict(scope='Paired FLEURS comparison; hardware scope recorded per experiment; not dialogue quality', experiments=[], comparisons=[])
    cases = []
    for experiment in args.experiments:
        path = ROOT / '.audio-runs' / experiment
        config = json.loads((path / 'config.json').read_text())
        rows = [json.loads(line) for line in (path / 'results.jsonl').read_text().splitlines()]
        manifest_path=ROOT/config.get('manifest','eval/data/fleurs-ru-validation.jsonl')
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=config['manifest_sha256']:raise ValueError('Changed manifest')
        manifest = [json.loads(line) for line in manifest_path.read_text().splitlines()]
        references={}
        for row in manifest:
            source=ROOT/row['reference']
            if hashlib.sha256(source.read_bytes()).hexdigest()!=row['reference_sha256']:raise ValueError('Changed reference')
            references[row['audio_id']]=source.read_text()
        for row in rows:
            if 'hypothesis' not in row:
                row['hypothesis']=dict(text=row['backend']['text']);row['reference']=references[row['audio_id']]
                row['normalized']=counts(row['reference'],row['hypothesis']['text'])
        by_id = {r['audio_id']: r for r in rows}
        ids = sorted(by_id)
        ordered = [by_id[i] for i in ids]
        if cases and ids != cases[0][0]:
            raise ValueError('Cannot compare experiments on different selected clips')
        groups = [next(r['source_id'] for r in manifest if r['audio_id'] == i) for i in ids]
        metrics = json.loads((ROOT/'eval/results'/experiment/'metrics.json').read_text())
        char_scores = [jiwer.process_characters(normalize(r['reference']), normalize(r['hypothesis']['text'])) for r in ordered]
        char_errors = sum(s.substitutions + s.deletions + s.insertions for s in char_scores)
        char_total = sum(s.hits + s.substitutions + s.deletions for s in char_scores)
        numeral = [r for r in rows if re.search(r'\d', r['reference'])]
        metrics.update(normalized_cer=char_errors / char_total,
                       reference_contains_digits=dict(clips=len(numeral), **aggregate([r['normalized'] for r in numeral])),
                       reference_without_digits=aggregate([r['normalized'] for r in rows if r not in numeral]))
        def error_count(r):return sum(r['normalized'][k] for k in ('substitutions','deletions','insertions'))
        metrics['worst_cases']=[dict(audio_id=r['audio_id'],**r['normalized'],reference_contains_digits=bool(re.search(r'\d',r['reference'])))
            for r in sorted(rows,key=lambda r:(error_count(r)/max(1,r['normalized']['reference_words']),error_count(r)),reverse=True)[:10]]
        report['experiments'].append(metrics)
        cases.append((ids, ordered, groups))
    for i in range(1, len(cases)):
        a, b = cases[0][1], cases[i][1]
        if any(x['reference'] != y['reference'] for x, y in zip(a, b)):
            raise ValueError('Reference texts differ')
        report['comparisons'].append(dict(a=args.experiments[0], b=args.experiments[i],
            **paired_interval(a, b, cases[0][2])))
    destination = args.output.resolve()
    if not destination.is_relative_to(ROOT) or destination.is_relative_to(ROOT/'task') or destination.exists():
        raise ValueError('Comparison output must be a new repository file outside task/')
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
