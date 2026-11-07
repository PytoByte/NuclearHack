#!/usr/bin/env python3
"""Audit standalone SDK host/device equivalence and fresh-process repeatability."""
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True)
    p.add_argument('--host', required=True)
    p.add_argument('--targets', nargs='+', required=True)
    args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment):
        p.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment
    out.mkdir(parents=True, exist_ok=False)
    config = dict(vars(args), input_sha256={}, scope='standalone x86 AVD speaker SDK repeatability; fixed host ASR; no ARM, coldboot or independent quality claim')
    record_harness(out, config)

    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
        return json.loads(path.read_text())

    host = ROOT/'.audio-runs'/args.host
    host_config = read(host/'config.json')
    host_provenance = read(host/'build-provenance.json')
    host_cases = {c['audio_id']: c for c in read(host/'metrics.json')['cases']}
    repeated = {}
    runtime = None
    cases = []
    for run in args.targets:
        directory = ROOT/'.audio-runs'/run
        actual = read(directory/'config.json')
        provenance = read(directory/'build-provenance.json')
        for name, digest in host_provenance['inputs'].items():
            if name.startswith('src/audio/') and provenance['inputs'].get(name) != digest:
                raise ValueError('Host/device native source differs: '+name)
        for field in ['manifest_sha256', 'model_files', 'profile', 'baseline']:
            if actual[field] != host_config[field]:
                raise ValueError('Comparison changes another factor: '+field)
        if runtime is not None and runtime != actual['device_runtime_sha256']:
            raise ValueError('Target repeated processes use different binaries')
        runtime = actual['device_runtime_sha256']
        metrics = read(directory/'metrics.json')
        if {c['audio_id'] for c in metrics['cases']} != set(host_cases):
            raise ValueError('Host/device case sets differ')
        for c in metrics['cases']:
            ident = c['audio_id']
            baseline = host_cases[ident]
            for field in ['source_samples', 'posterior_frames', 'decoded_pcm_sha256', 'speaker_attributed']:
                if baseline[field] != c[field]:
                    raise ValueError('Host/device source/attribution differs: '+field)
            source = host/ident/'posteriors.f32'
            candidate = directory/ident/'posteriors.f32'
            for path in [source, candidate]:
                config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
            a = np.fromfile(source, dtype='<f4').reshape(-1, 8)
            b = np.fromfile(candidate, dtype='<f4').reshape(-1, 8)
            if a.shape != b.shape or np.any((a>.5)!=(b>.5)):
                raise ValueError('Host/device posterior time grid/threshold decisions differ')
            if ident in repeated and not np.array_equal(repeated[ident], b):
                raise ValueError('Repeated target process is not numerically deterministic')
            repeated[ident] = b
            memory_path = directory/ident/'memory.jsonl'
            config['input_sha256'][str(memory_path.relative_to(ROOT))] = sha256(memory_path)
            memory = [json.loads(line) for line in memory_path.read_text().splitlines()]
            times = [row['uptime_seconds'] for row in memory]
            periods = [1000*(b-a) for a, b in zip(times, times[1:]) if b>a]
            if not memory:
                raise ValueError('No target PSS samples captured')
            cases.append(dict(experiment=run, audio_id=ident, processing_seconds=c['processing_seconds'],
                              inference_rtf=c['inference_rtf'], load_seconds=c['load_seconds'],
                              sampled_peak_pss_kib=max(row['pss_kib'] for row in memory),
                              process_peak_rss_kib=c['process_peak_rss_kib'], memory_samples=len(memory),
                              actual_median_sample_interval_ms=statistics.median(periods) if periods else None,
                              host_max_posterior_delta=float(abs(a-b).max(initial=0)),
                              cpwer=c['speaker_attributed']['cpwer'], der=c.get('der_details',{}).get('diarization error rate'), jer=c.get('jer')))
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases,
                   source_and_native_code_verified=True, target_posteriors_repeat_exact=True,
                   host_target_threshold_decisions_exact=True,
                   processing_seconds_range=[min(c['processing_seconds'] for c in cases), max(c['processing_seconds'] for c in cases)],
                   median_processing_seconds=statistics.median(c['processing_seconds'] for c in cases),
                   median_inference_rtf=statistics.median(c['inference_rtf'] for c in cases),
                   maximum_sampled_pss_kib=max(c['sampled_peak_pss_kib'] for c in cases),
                   maximum_process_rss_kib=max(c['process_peak_rss_kib'] for c in cases),
                   limitation='three fresh processes, OS file cache retained; observed timing spread is descriptive, no causal speedup inference')
    report = ROOT/'eval/results'/args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2))
        (report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics, indent=2))


if __name__ == '__main__':
    main()
