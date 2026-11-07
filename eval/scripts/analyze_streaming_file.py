#!/usr/bin/env python3
"""Audit complete file API quality parity, source identity and target repetitions."""
import argparse
import json
import re
import statistics
import sys
import numpy as np
from native_sdk import ROOT, record_harness
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--experiment', required=True); args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment): p.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment; out.mkdir(parents=True, exist_ok=False)
    config = dict(vars(args), seed=42, bootstrap_samples=10000, input_sha256={},
        scope='complete native file API audit; six known RU silver quality cases and three fresh x86AVD processes, no ARM/coldboot/independent gold claim')
    record_harness(out, config)
    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
        return json.loads(path.read_text())
    previous = {}
    for n in [99, 101, 104, 155]:
        for c in read(ROOT/f'eval/results/exp_{n:04d}/metrics.json')['cases']: previous[c['audio_id']] = c
    cases = []
    for n in [205, 206, 207, 208]:
        for c in read(ROOT/f'eval/results/exp_{n:04d}/metrics.json')['cases']:
            if not c['baseline_words_exact'] or not c['prototype_slots_exact']: raise ValueError('Native prototype parity failed')
            baseline = previous[c['audio_id']]['speaker_attributed']
            score = c['speaker_attributed']
            if baseline['reference_words'] != score['reference_words']: raise ValueError('Reference differs')
            cases.append(dict(audio_id=c['audio_id'], reference_words=score['reference_words'],
                previous_eres_errors=baseline['errors'], native_posterior_errors=score['errors'],
                exact_asr_words_and_prototype_slots=True, full_rtf=c['full_rtf']))
    if {c['audio_id'] for c in cases} != set(previous): raise ValueError('Different source sets')
    old = read(ROOT/'.audio-runs/exp_0186/ru-youtube-movie_podcast/transcript.json')
    reproduced = read(ROOT/'.audio-runs/exp_0203/ru-youtube-movie_podcast/transcript.json')
    if old != reproduced: raise ValueError('Old default API regressed')
    controls = read(ROOT/'eval/results/exp_0209/metrics.json')
    if not controls['passed']: raise ValueError('New file API controls failed')
    host = ROOT/'.audio-runs/exp_0210'
    host_config = read(host/'config.json'); host_build = read(host/'build-provenance.json')
    targets = []; first = None; runtime = None
    for run in ['exp_0211', 'exp_0212', 'exp_0213']:
        directory = ROOT/'.audio-runs'/run
        actual = read(directory/'config.json'); build = read(directory/'build-provenance.json')
        for name, digest in host_build['inputs'].items():
            if name.startswith('src/audio/') and build['inputs'].get(name) != digest: raise ValueError('Native host/device code differs')
        for key in ['model_files', 'manifest_sha256', 'threads', 'profile', 'word_anchor_ms']:
            if actual[key] != host_config[key]: raise ValueError('Device run changes '+key)
        if runtime is not None and runtime != actual['device_runtime_sha256']: raise ValueError('Target binaries differ')
        runtime = actual['device_runtime_sha256']
        c = read(directory/'metrics.json')['cases'][0]
        if not c['host_comparison']['source_pcm_exact']: raise ValueError('Host/device PCM differs')
        ident = c['audio_id']; trace = read(directory/ident/'transcript.json.trace.json')
        transcript = read(directory/ident/'transcript.json')
        payload = dict(transcript=transcript, words=trace['words'], slots=trace['word_speaker_slots'], turns=trace['speaker_turns'])
        if first is not None and payload != first: raise ValueError('Repeated target results are not exact')
        first = payload
        memory = directory/ident/'memory.jsonl'; config['input_sha256'][str(memory.relative_to(ROOT))] = sha256(memory)
        samples = list(map(json.loads, memory.read_text().splitlines()))
        intervals = [(b['uptime_seconds']-a['uptime_seconds'])*1000 for a,b in zip(samples,samples[1:])]
        targets.append(dict(experiment=run, processing_seconds=c['wall_seconds'], full_rtf=c['full_rtf'],
            pss_kib=c['sampled_peak_pss_kib'], process_peak_rss_kib=c['process_peak_rss_kib'],
            median_sample_interval_ms=statistics.median(intervals) if intervals else None,
            normalized_wer=c['text_metrics']['normalized'], cpwer=c['speaker_attributed']['cpwer'], host_comparison=c['host_comparison']))
    count = sum(c['reference_words'] for c in cases)
    old_errors = sum(c['previous_eres_errors'] for c in cases); new_errors = sum(c['native_posterior_errors'] for c in cases)
    rng = np.random.default_rng(42); indices = rng.integers(0, len(cases), size=(10000,len(cases)))
    weights = np.array([c['reference_words'] for c in cases]); delta = np.array([c['native_posterior_errors']-c['previous_eres_errors'] for c in cases])
    boot = delta[indices].sum(axis=1)/weights[indices].sum(axis=1)
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases,
        previous_eres_cpwer=old_errors/count, native_posterior_cpwer=new_errors/count,
        delta_cpwer=(new_errors-old_errors)/count, record_bootstrap_ci95=list(map(float,np.quantile(boot,[.025,.975]))),
        old_default_json_exact=True, controls_passed=True, targets=targets, target_transcript_words_slots_turns_repeat_exact=True,
        median_target_full_rtf=statistics.median(t['full_rtf'] for t in targets),
        target_seconds_range=[min(t['processing_seconds'] for t in targets), max(t['processing_seconds'] for t in targets)],
        maximum_target_pss_kib=max(t['pss_kib'] for t in targets),
        limitation='Small known silver source files, unverified speaker independence; all target ASR truly runs on device; no physical ARM or hourly stress claim.')
    report = ROOT/'eval/results'/args.experiment; report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2)); (report/name).write_bytes((out/name).read_bytes())
    print(json.dumps({k:v for k,v in metrics.items() if k not in ['cases', 'targets']}), flush=True)


if __name__ == '__main__': main()
