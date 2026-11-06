#!/usr/bin/env python3
"""Execute the same pipeline through APK/JNI on the isolated 4-GB AVD."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from native_sdk import ROOT
from scoring import aggregate, counts
from run_file_pipeline import cpwer
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_android_audio import environment
from bootstrap_models import sha256
from audio_tools import transcript as validate_transcript

PACKAGE = 'com.hexteam.audiohost'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--threshold', type=float, default=0.8)
    parser.add_argument('--chunk-seconds', type=int, default=20)
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args()
    if not args.experiment.startswith('exp_') or not args.experiment[4:].isdigit():
        parser.error('Use exp_NNNN')
    out = ROOT / '.audio-runs' / args.experiment
    out.mkdir(parents=True, exist_ok=False)
    env = environment()
    adb = [str(ROOT / '.tools/android-sdk/platform-tools/adb'), '-P', '5039', '-s', 'emulator-5558']
    def shell(*command): return subprocess.check_output(adb + ['shell', *command], env=env, text=True)
    abi = shell('getprop', 'ro.product.cpu.abi').strip()
    memory = shell('cat', '/proc/meminfo')
    if abi != 'x86_64' or shell('getprop', 'ro.kernel.qemu').strip() != '1':
        raise RuntimeError('Expected isolated x86_64 Android emulator')
    if shell('settings', 'get', 'global', 'airplane_mode_on').strip() != '1':
        raise RuntimeError('Offline test requires airplane mode')
    config = dict(experiment_id=args.experiment, threads=args.threads, threshold=args.threshold,
        chunk_seconds=args.chunk_seconds, summary=args.summary, abi=abi, avd_configured_ram_mib=4096,
        manifest_sha256=sha256(ROOT / 'eval/data/dialogs-smoke.jsonl'),
        apk_sha256=sha256(ROOT / '.build/android-host/audio-sdk-host.apk'),
        model_lock_sha256=sha256(ROOT / 'config/audio-models.lock.json'))
    (out / 'config.json').write_text(json.dumps(config, indent=2))
    (out / 'environment.json').write_text(json.dumps(dict(meminfo=memory, cpuinfo=shell('cat','/proc/cpuinfo'),
        build=shell('getprop','ro.build.fingerprint'), airplane_mode=True,
        git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()), indent=2))
    command = adb + ['shell', 'am', 'instrument', '-w', '-r', '-e', 'run_id', args.experiment,
        '-e', 'config_hash', hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        '-e', 'threads', str(args.threads), '-e', 'threshold', str(args.threshold),
        '-e', 'chunk_seconds', str(args.chunk_seconds), '-e', 'summary', '1' if args.summary else '0',
        PACKAGE + '/.AudioInstrumentation']
    with (out / 'stdout.log').open('w') as stdout, (out / 'stderr.log').open('w') as stderr:
        result = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=1800)
    text = (out / 'stdout.log').read_text()
    subprocess.run(adb + ['logcat', '-d', '-t', '3000'], env=env, stdout=(out / 'logcat.txt').open('w'))
    if result.returncode or 'INSTRUMENTATION_RESULT: result=PASS' not in text:
        (out / 'failure.json').write_text(json.dumps(dict(exit_code=result.returncode, stage='instrumentation',
            stdout_tail=text[-3000:]), indent=2))
        raise RuntimeError('Android pipeline failed; see ' + str(out))
    def pull(name):
        data = subprocess.check_output(adb + ['exec-out','run-as',PACKAGE,'cat',
            'files/results/' + args.experiment + '/' + name], env=env)
        path = out / name; path.write_bytes(data); return path
    metrics = json.loads(pull('metrics.json').read_text())
    fixtures = {r['audio_id']:r for r in (json.loads(l) for l in (ROOT/'eval/data/dialogs-smoke.jsonl').read_text().splitlines())}
    for case in metrics['cases']:
        name = case['audio_id']
        output = json.loads(pull(name + '.json').read_text()); validate_transcript(output)
        trace = json.loads(pull(name + '.json.trace.json').read_text())
        pull(name + '.events.jsonl')
        if args.summary: pull(name + '.summary.txt')
        truth = json.loads((ROOT / fixtures[name]['reference']).read_text())['transcript']
        case['normalized'] = counts(' '.join(r['text'] for r in truth), ' '.join(r['text'] for r in output['transcript']))
        case['speaker_attributed'] = cpwer(truth, output['transcript'])
        case['audio_seconds'] = max((r['offset_frames'] + r['frames']) / 16000 for r in trace['asr'])
        case['full_rtf'] = case['wall_ms'] / 1000 / case['audio_seconds']
        case['predicted_speakers'] = len({r['speaker_id'] for r in output['transcript']})
        case['expected_speakers'] = fixtures[name]['speakers']
        case['json_valid'] = True
    metrics['normalized'] = aggregate([c['normalized'] for c in metrics['cases']])
    (out / 'scored-metrics.json').write_text(json.dumps(metrics, indent=2))
    report = ROOT / 'eval/results' / args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for source, target in [('scored-metrics.json','metrics.json'),('config.json','config.json'),('environment.json','environment.json')]:
        (report / target).write_bytes((out/source).read_bytes())
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == '__main__':
    main()
