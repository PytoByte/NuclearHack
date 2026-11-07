#!/usr/bin/env python3
"""Research-only repeated short-turn novelty; anchors and rules never use gold."""
import argparse
import json
import time
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from native_sdk import ROOT, NativeSdk, record_build
from probe_reclustering import Extractor, diarization
from probe_attribution import attribute
from run_file_pipeline import cpwer
from scoring import normalize, speaker_coverage
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import sha256


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True)
    p.add_argument('--baseline', required=True)
    p.add_argument('--manifest', required=True)
    args = p.parse_args()
    import re
    if not re.fullmatch(r'exp_[0-9]+', args.experiment):
        p.error('Use exp_NNNN')
    out = ROOT / '.audio-runs' / args.experiment
    out.mkdir(parents=True, exist_ok=False)
    model_path = 'models/diarization/embedding.onnx'
    model = next(f for f in json.loads((ROOT / 'config/audio-models.lock.json').read_text())['files'] if f['path'] == model_path)
    if sha256(ROOT / model_path) != model['sha256']:
        raise ValueError('Embedding hash differs')
    config = dict(vars(args), model_files=[model], manifest_sha256=sha256(ROOT / args.manifest),
                  sdk_sha256=sha256(ROOT / '.build/audio/libnuclear_audio.so'), input_sha256={},
                  anchor_min_ms=1500, anchor_min_seconds=2, anchor_spans=3, anchor_span_max_ms=8000,
                  candidate_min_ms=300, candidate_max_ms=1500, novelty_threshold=.4,
                  complete_link_threshold=.25, min_repeated_turns=2, min_group_ms=1000,
                  min_start_separation_ms=2000, threads=4,
                  scope='research selective short-turn split; no reference inputs; no SDK integration')
    record_build(out, config)
    sdk = NativeSdk()
    started = time.perf_counter()
    extract = Extractor(sdk, ROOT / model_path)
    load_seconds = time.perf_counter() - started
    cases = []
    try:
        for f in map(json.loads, (ROOT / args.manifest).read_text().splitlines()):
            trace_path = ROOT / '.audio-runs' / args.baseline / f['audio_id'] / 'transcript.json.trace.json'
            config['input_sha256'][str(trace_path.relative_to(ROOT))] = sha256(trace_path)
            if sha256(ROOT / f['audio']) != f['audio_sha256'] or sha256(ROOT / f['reference']) != f['reference_sha256']:
                raise ValueError('Changed corpus')
            trace = json.loads(trace_path.read_text())
            pcm = sdk.decode(ROOT / f['audio'], max_frames=180*16000+16)
            if len(pcm) >= 180*16000+16:
                raise ValueError('Clip exceeds research budget')
            duration = len(pcm) / 16000
            if f.get('audio_seconds') is not None and abs(duration-f['audio_seconds']) > .002:
                raise ValueError('Decoded duration differs')
            turns = [dict(start_ms=t['start_ms'], end_ms=t['end_ms'], speaker_id=str(t['speaker'])) for t in trace['speaker_turns']]
            changed = [dict(t) for t in turns]
            started = time.perf_counter()
            anchors = {}
            for speaker in sorted({t['speaker_id'] for t in turns}):
                spans = sorted([t for t in turns if t['speaker_id'] == speaker and t['end_ms']-t['start_ms'] >= 1500], key=lambda t: t['end_ms']-t['start_ms'], reverse=True)[:3]
                pieces = []
                for t in spans:
                    width = min(8000, t['end_ms']-t['start_ms'])
                    left = t['start_ms'] + (t['end_ms']-t['start_ms']-width)//2
                    pieces.append(pcm[max(0, left)*16:(left+width)*16])
                if pieces:
                    samples = np.concatenate(pieces)[:320000]
                    if len(samples) >= 32000:
                        vector = extract(samples)
                        if vector is not None:
                            anchors[speaker] = vector
            candidates, vectors, evidence = [], [], []
            for i, t in enumerate(turns):
                width = t['end_ms']-t['start_ms']
                if not 300 <= width <= 1500 or t['speaker_id'] not in anchors:
                    continue
                if any(i != j and min(t['end_ms'], u['end_ms']) > max(t['start_ms'], u['start_ms']) for j, u in enumerate(turns)):
                    continue
                vector = extract(pcm[max(0, t['start_ms'])*16:t['end_ms']*16])
                if vector is None:
                    continue
                distances = {speaker: float(np.clip(1-np.dot(vector, anchor), 0, 2)) for speaker, anchor in anchors.items()}
                novel = min(distances.values()) > .4
                evidence.append(dict(turn_index=i, distances=distances, novel=novel))
                if novel:
                    candidates.append(i)
                    vectors.append(vector)
            accepted = []
            if candidates:
                matrix = np.clip(1-np.asarray(vectors) @ np.asarray(vectors).T, 0, 2)
                matrix = (matrix+matrix.T)/2
                np.fill_diagonal(matrix, 0)
                groups = fcluster(linkage(squareform(matrix, checks=False), method='complete'), t=.25, criterion='distance') if len(candidates)>1 else [1]
                for group in sorted(set(groups)):
                    indexes = [i for i, g in zip(candidates, groups) if g == group]
                    enough = len(indexes) >= 2 and sum(turns[i]['end_ms']-turns[i]['start_ms'] for i in indexes) >= 1000
                    separated = max(turns[i]['start_ms'] for i in indexes)-min(turns[i]['start_ms'] for i in indexes) >= 2000
                    if enough and separated:
                        label = 'short_novel_' + str(len(accepted))
                        for i in indexes:
                            changed[i]['speaker_id'] = label
                        accepted.append(indexes)
            seconds = time.perf_counter()-started
            truth = json.loads((ROOT / f['reference']).read_text())['transcript']
            variants = {}
            for name, rows in [('baseline', turns), ('selective', changed)]:
                predicted = attribute(trace['words'], rows)
                if normalize(' '.join(t['text'] for t in predicted)) != normalize(' '.join(w['text'] for w in trace['words'])):
                    raise ValueError('Changed lexical sequence')
                variants[name] = dict(speaker_attributed=cpwer(truth, predicted), **speaker_coverage(predicted))
                if f.get('rttm'):
                    variants[name].update(diarization(truth, rows, duration))
            (out / (f['audio_id']+'.evidence.json')).write_text(json.dumps(dict(anchors=list(anchors), candidates=evidence, accepted=accepted), indent=2))
            cases.append(dict(audio_id=f['audio_id'], refinement_seconds=seconds, anchored_speakers=len(anchors), candidate_turns=len(candidates), new_speakers=len(accepted), variants=variants))
    finally:
        extract.close()
    aggregate = {name: dict(cpwer=sum(c['variants'][name]['speaker_attributed']['errors'] for c in cases)/sum(c['variants'][name]['speaker_attributed']['reference_words'] for c in cases)) for name in ['baseline', 'selective']}
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], load_seconds=load_seconds, cases=cases, variants=aggregate)
    report = ROOT / 'eval/results' / args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2))
        (report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(aggregate, indent=2))


if __name__ == '__main__':
    main()
