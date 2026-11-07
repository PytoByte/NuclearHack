#!/usr/bin/env python3
"""End-to-end MP3 -> native ASR/diarization -> strict JSON, with process profiling."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import threading
import time

from scipy.optimize import linear_sum_assignment
from native_sdk import ROOT,record_build
from scoring import aggregate, counts, normalize, speaker_coverage, text_metrics
import jiwer
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import sha256
from audio_tools import transcript as validate_transcript


def profile(command, directory):
    peak_pss, sampled_rss = [], []
    stopped = threading.Event()
    with (directory / 'stdout.log').open('wb') as stdout, (directory / 'stderr.log').open('wb') as stderr:
        start = time.perf_counter()
        child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        def monitor():
            while not stopped.is_set():
                try:
                    values = dict((line.split(':', 1)[0], line.split(':', 1)[1]) for line in
                                  Path(f'/proc/{child.pid}/smaps_rollup').read_text().splitlines() if ':' in line)
                    peak_pss.append(int(values['Pss'].split()[0]))
                    sampled_rss.append(int(values['Rss'].split()[0]))
                except (OSError, KeyError, ValueError):
                    pass
                stopped.wait(0.05)
        observer = threading.Thread(target=monitor)
        observer.start()
        _, status, usage = os.wait4(child.pid, 0)
        child.returncode = os.waitstatus_to_exitcode(status)
        stopped.set(); observer.join()
        duration = time.perf_counter() - start
    return dict(exit_code=child.returncode, wall_seconds=duration, process_peak_rss_kib=usage.ru_maxrss,
                sampled_peak_pss_kib=max(peak_pss) if peak_pss else None,
                sampled_peak_rss_kib=max(sampled_rss) if sampled_rss else None, pss_sample_period_ms=50)


def cpwer(reference, hypothesis):
    refs, hyps = {}, {}
    for row in reference:
        refs.setdefault(row['speaker_id'], []).append(row['text'])
    for row in hypothesis:
        hyps.setdefault(row['speaker_id'], []).append(row['text'])
    a, b = [' '.join(v) for v in refs.values()], [' '.join(v) for v in hyps.values()]
    n = max(len(a), len(b))
    if not n:return dict(errors=0,reference_words=0,cpwer=None)
    a += [''] * (n - len(a)); b += [''] * (n - len(b))
    costs = []
    for left in a:
        row = []
        for right in b:
            score = jiwer.process_words(normalize(left), normalize(right))
            row.append(score.substitutions + score.deletions + score.insertions)
        costs.append(row)
    i, j = linear_sum_assignment(costs)
    errors = sum(costs[x][y] for x, y in zip(i, j))
    total = sum(len(normalize(t).split()) for t in a)
    return dict(errors=int(errors), reference_words=total, cpwer=errors / total if total else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--manifest', type=Path, default=ROOT/'eval/data/dialogs-smoke.jsonl')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--threshold', type=float, default=0.8)
    parser.add_argument('--chunk-seconds', type=int, default=20)
    parser.add_argument('--summary', action='store_true')
    parser.add_argument('--embedding',default='embedding.onnx')
    parser.add_argument('--min-on',type=float,default=0.3)
    parser.add_argument('--min-off',type=float,default=0.5)
    parser.add_argument('--attribution',choices=['overlap','midpoint'],default='overlap')
    parser.add_argument('--window-shift-ratio',type=float,default=0.1)
    parser.add_argument('--model',default='giga-v3-ctc')
    parser.add_argument('--quant',choices=['fp32','int8'],default='fp32')
    args = parser.parse_args()
    if not args.experiment.startswith('exp_') or not args.experiment[4:].isdigit():
        parser.error('Use exp_NNNN')
    manifest = args.manifest.resolve()
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    catalog=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    model=next(m for m in catalog['models'] if m['id']==args.model)
    if model['family']!='ctc':parser.error('File pipeline currently supports CTC; other models use ASR API')
    asr_path=next(p for p in model.get('runtime_files',model['files']) if Path(p).name in ('model.int8.onnx','model.onnx'))
    tokens_path=next(p for p in model['files'] if Path(p).name=='tokens.txt')
    seg_path='models/diarization/'+('segmentation-model.onnx' if args.quant=='fp32' else 'segmentation-model.int8.onnx')
    selected={asr_path,tokens_path,seg_path,'models/diarization/'+args.embedding}
    model_files=[f for f in catalog['files'] if f['path'] in selected]
    if len(model_files)!=len(selected):raise ValueError('Unpinned pipeline model')
    for item in model_files:
        if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Changed pipeline model')
    out = ROOT / '.audio-runs' / args.experiment
    out.mkdir(parents=True, exist_ok=False)
    config = dict(experiment_id=args.experiment, threads=args.threads, threshold=args.threshold,
        embedding=args.embedding,min_duration_on=args.min_on,min_duration_off=args.min_off,attribution=args.attribution,
        model=args.model,quant=args.quant,model_files=model_files,window_shift_ratio=args.window_shift_ratio,
        chunk_seconds=args.chunk_seconds, summary=args.summary, manifest_sha256=sha256(manifest),
        sdk_sha256=sha256(ROOT / '.build/audio/libnuclear_audio.so'),
        model_lock_sha256=sha256(ROOT / 'config/audio-models.lock.json'),
        scope='Linux native file pipeline; reference quality and split limits follow manifest', manifest=str(manifest.relative_to(ROOT)))
    record_build(out,config)
    (out / 'config.json').write_text(json.dumps(config, indent=2))
    metrics = []
    for row in rows:
        case = out / row['audio_id']; case.mkdir()
        audio = ROOT / row['audio']; reference = ROOT / row['reference']
        if sha256(audio) != row['audio_sha256'] or sha256(reference) != row['reference_sha256']:
            raise ValueError('Fixture checksum mismatch')
        output = case / 'transcript.json'
        command = [str(ROOT / '.build/audio/nh-audio'), 'transcribe', str(audio), str(output),
            asr_path, tokens_path,seg_path, 'models/diarization/'+args.embedding,
            str(case), str(args.threads), str(args.threshold), str(args.chunk_seconds),str(args.min_on),str(args.min_off),
            '1' if args.attribution=='midpoint' else '0','600','-',str(args.window_shift_ratio)]
        timing = profile(command, case)
        if timing['exit_code']:
            (case / 'failure.json').write_text(json.dumps(timing, indent=2))
            raise RuntimeError('Native file pipeline failed; see ' + str(case / 'stderr.log'))
        actual = json.loads(output.read_text()); validate_transcript(actual)
        truth = json.loads(reference.read_text())['transcript']
        asr = counts(' '.join(t['text'] for t in truth), ' '.join(t['text'] for t in actual['transcript']))
        trace = json.loads(output.with_name(output.name + '.trace.json').read_text())
        duration = max((s['offset_frames'] + s['frames']) / 16000 for s in trace['asr'])
        result = dict(audio_id=row['audio_id'], **timing, audio_seconds=duration,
            full_rtf=timing['wall_seconds'] / duration, normalized=asr,
            speaker_attributed=cpwer(truth, actual['transcript']),
            expected_speakers=row['speakers'], predicted_speakers=len({t['speaker_id'] for t in actual['transcript']}),
            **speaker_coverage(actual['transcript']),
            text_metrics=text_metrics(' '.join(t['text'] for t in truth), ' '.join(t['text'] for t in actual['transcript'])),
            json_valid=True, transcript_sha256=sha256(output),
            alignment_fallback_chunks=sum(s['alignment'] not in ('ctc_chars','ctc_tokens') for s in trace['asr']))
        if args.summary:
            before = sha256(output)
            summary_dir = case / 'llm'; summary_dir.mkdir()
            result['summary'] = profile([str(ROOT / '.build/audio/nh-audio'), 'summarize', str(output),
                'models/qwen3-0.6b-q8/Qwen3-0.6B-Q8_0.gguf', str(case / 'summary.txt'), str(args.threads)], summary_dir)
            result['summary']['main_transcript_unchanged'] = before == sha256(output)
        metrics.append(result)
        with (out / 'results.jsonl').open('a') as target:
            target.write(json.dumps(result) + '\n')
        print(json.dumps(result), flush=True)
    total = dict(experiment_id=args.experiment, cases=metrics, normalized=aggregate([r['normalized'] for r in metrics]),
                 scope=config['scope'])
    (out / 'metrics.json').write_text(json.dumps(total, indent=2))
    (out / 'environment.json').write_text(json.dumps(dict(
        git_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        git_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))), indent=2))
    report = ROOT / 'eval/results' / args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for name in ('metrics.json', 'config.json', 'environment.json'):
        (report / name).write_bytes((out / name).read_bytes())


if __name__ == '__main__':
    main()
