#!/usr/bin/env python3
"""Compare an intact official CPU pipeline, preserving its own ASR and timings."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from native_sdk import ROOT, record_harness
from run_file_pipeline import cpwer
from scoring import normalize, text_metrics, speaker_coverage
from compare_punctuation import summarize
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256


def words_to_transcript(result):
    words = result['words']
    if normalize(' '.join(w['word'] for w in words)) != normalize(result['text']):
        raise ValueError('Official word list does not reproduce full transcript; cannot claim cpWER')
    rows = []
    for w in words:
        start, end = w['start'], w['end']
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end <= result['duration']+.02):
            raise ValueError('Official word times outside source timeline')
        speaker = w.get('speaker', 0)
        rows.append(dict(speaker_id='speaker_'+str(speaker) if speaker > 0 else 'speaker_unknown',
                         start_ms=round(start*1000), end_ms=round(end*1000), text=w['word']))
    return rows


def profile(command, folder, timeout):
    stopped = threading.Event()
    samples = []
    with (folder/'stdout.json').open('wb') as stdout, (folder/'stderr.log').open('wb') as stderr:
        began = time.perf_counter()
        child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        expired = threading.Event()
        def kill():
            expired.set()
            try: child.kill()
            except ProcessLookupError: pass
        timer = threading.Timer(timeout, kill)
        timer.start()
        def observe():
            while not stopped.is_set():
                try:
                    lines = Path(f'/proc/{child.pid}/smaps_rollup').read_text().splitlines()
                    value = {line.split(':')[0]: line.split(':')[1].split()[0] for line in lines if ':' in line}
                    samples.append(dict(seconds=time.perf_counter()-began, pss_kib=int(value['Pss']), rss_kib=int(value['Rss'])))
                except (OSError, KeyError, ValueError): pass
                stopped.wait(.05)
        watcher = threading.Thread(target=observe)
        watcher.start()
        try:
            _, status, usage = os.wait4(child.pid, 0)
            child.returncode = os.waitstatus_to_exitcode(status)
        finally:
            timer.cancel(); stopped.set(); watcher.join()
        wall = time.perf_counter()-began
    (folder/'memory.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in samples))
    timing = dict(exit_code=child.returncode, timed_out=expired.is_set(), wall_seconds=wall,
                  process_peak_rss_kib=usage.ru_maxrss,
                  sampled_peak_pss_kib=max((s['pss_kib'] for s in samples), default=None), memory_samples=len(samples))
    (folder/'timing.json').write_text(json.dumps(timing, indent=2))
    if child.returncode or expired.is_set():
        raise RuntimeError('Official CLI failed; raw stdout/stderr/timing retained')
    return timing


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True)
    p.add_argument('--stream', action='store_true')
    p.add_argument('--diarize', action='store_true')
    p.add_argument('--manifest', default='eval/data/russian-conversation-movie-session.jsonl')
    p.add_argument('--timeout', type=int, default=1200)
    args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment): p.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment
    out.mkdir(parents=True, exist_ok=False)
    runtime = ROOT/'.tools/nemo-reference/0.3.0'
    provenance = json.loads((runtime/'reference-provenance.json').read_text())
    for name, digest in provenance['files'].items():
        if sha256(runtime/name) != digest: raise ValueError('Reference runtime file changed: '+name)
    lock = json.loads((ROOT/'config/audio-models.lock.json').read_text())
    ids = ['nemotron35-asr-q8'] + (['nemotron3-diarization-gguf-q8'] if args.diarize else [])
    models = [next(m for m in lock['models'] if m['id'] == name) for name in ids]
    files = [next(f for f in lock['files'] if f['path'] == path) for m in models for path in m['files']]
    for f in files:
        if sha256(ROOT/f['path']) != f['sha256']: raise ValueError('Reference model changed')
    config = dict(vars(args), runtime=provenance, model_files=files, model_lock_sha256=sha256(ROOT/'config/audio-models.lock.json'),
                  manifest_sha256=sha256(ROOT/args.manifest), threads=4, backend='cpu', language='ru-RU',
                  scope='official NeMo-Speech.cpp 0.3.0 native CPU reference; host x86_64, not SDK/Android/ARM qualification',
                  no_warmup=True, batching=False, itn=False, diarization_preset='v3-offline' if args.diarize else None,
                  input_sha256={})
    record_harness(out, config)
    (out/'config.json').write_text(json.dumps(config, indent=2))
    cases = []
    for f in map(json.loads, (ROOT/args.manifest).read_text().splitlines()):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', f['audio_id']): raise ValueError('Invalid audio ID')
        for field in ['audio', 'reference']:
            if sha256(ROOT/f[field]) != f[field+'_sha256']: raise ValueError('Changed frozen fixture')
        folder = out/f['audio_id']; folder.mkdir()
        command = [str(runtime/'bin/nemo-speech'), 'transcribe', str(ROOT/f['audio']), '--model', str(ROOT/files[0]['path']),
                   '--backend', 'cpu', '--language', 'ru-RU', '--asr.backend.threads', '4', '--format', 'json',
                   '--no-warmup', '--no-batching', '--verbatim']
        if args.stream: command.append('--stream')
        if args.diarize:
            command += ['--diar-model', str(ROOT/files[1]['path']), '--asr.diar.preset', 'v3-offline']
        (folder/'command.json').write_text(json.dumps(command, indent=2))
        timing = profile(command, folder, args.timeout)
        result = json.loads((folder/'stdout.json').read_text())
        if abs(result['duration']-f['audio_seconds']) > .02: raise ValueError('Official decoded duration differs')
        truth = json.loads((ROOT/f['reference']).read_text())['transcript']
        case = dict(audio_id=f['audio_id'], **timing, audio_seconds=f['audio_seconds'], full_rtf=timing['wall_seconds']/f['audio_seconds'],
                    text_metrics=text_metrics(' '.join(t['text'] for t in truth), result['text']),
                    languages=result['languages'], word_count=len(result['words']))
        words = words_to_transcript(result)
        case['word_text_reconstruction_equal'] = True
        if args.diarize:
            case.update(speaker_attributed=cpwer(truth, words), **speaker_coverage(words))
            case['der_unavailable_reason'] = 'ASR JSON exposes word labels, not raw diarizer frame spans; do not invent DER from words'
        (folder/'words.json').write_text(json.dumps(words, indent=2))
        cases.append(case)
        print(json.dumps(dict(audio_id=f['audio_id'], rtf=case['full_rtf'], text=case['text_metrics']['normalized'])), flush=True)
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases,
                   text_metrics=summarize([c['text_metrics'] for c in cases]),
                   inference_rtf=sum(c['wall_seconds'] for c in cases)/sum(c['audio_seconds'] for c in cases),
                   process_peak_rss_kib=max(c['process_peak_rss_kib'] for c in cases))
    metrics['normalized'] = metrics['text_metrics']['normalized']
    metrics['cer'] = metrics['text_metrics']['normalized_cer']['cer']
    report = ROOT/'eval/results'/args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2)); (report/name).write_bytes((out/name).read_bytes())


if __name__ == '__main__': main()
