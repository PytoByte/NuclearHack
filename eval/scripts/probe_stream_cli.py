#!/usr/bin/env python3
"""Profile the standalone speaker SDK CLI, on host or isolated offline 4GB x86 AVD.

Speaker attribution reuses frozen host ASR words. It is not target ASR or ARM
quality. Each CLI is a fresh process; OS page cache is not cleared.
"""
import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
import numpy as np
from native_sdk import ROOT, record_harness
from android_device import AndroidDevice
from probe_sortformer import turns_from_probs
from probe_attribution import attribute
from probe_reclustering import diarization
from run_file_pipeline import cpwer
from scoring import normalize, speaker_coverage
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256


def device_script(command, result_dir):
    """A fresh native child with in-device PSS sampling and durable exit status."""
    workload = shlex.join(command)
    return f''': > {shlex.quote(result_dir+'/memory.jsonl')}
{workload} > {shlex.quote(result_dir+'/stdout.json')} 2> {shlex.quote(result_dir+'/stderr.log')} &
stream_pid=$!
echo "$stream_pid" > {shlex.quote(result_dir+'/pid')}
while kill -0 "$stream_pid" 2>/dev/null; do
  stream_state=$(awk '{{print $3}}' "/proc/$stream_pid/stat" 2>/dev/null)
  [ "$stream_state" = Z ] && break
  if cat "/proc/$stream_pid/smaps_rollup" > {shlex.quote(result_dir+'/mem.tmp')} 2>/dev/null; then
    read stream_uptime stream_idle < /proc/uptime
    awk -v t="$stream_uptime" '/^Pss:/ {{p=$2}} /^Rss:/ {{r=$2}} END {{if(p>0) printf "{{\\\"uptime_seconds\\\":%s,\\\"pss_kib\\\":%d,\\\"rss_kib\\\":%d}}\\n",t,p,r}}' {shlex.quote(result_dir+'/mem.tmp')} >> {shlex.quote(result_dir+'/memory.jsonl')}
  fi
  sleep 0.05
done
wait "$stream_pid"
stream_status=$?
echo "$stream_status" > {shlex.quote(result_dir+'/exit-code')}
exit "$stream_status"
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True)
    p.add_argument('--android', action='store_true')
    p.add_argument('--manifest', default='eval/data/russian-conversation-movie-session.jsonl')
    p.add_argument('--baseline', default='exp_0101')
    p.add_argument('--profile', choices=['buffered', 'low'], default='buffered')
    p.add_argument('--model', choices=['nemotron3-diarization-q8', 'nemotron3-diarization-q4'], default='nemotron3-diarization-q8')
    p.add_argument('--host-reference')
    p.add_argument('--timeout', type=int, default=1200)
    args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment):
        p.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment
    out.mkdir(parents=True, exist_ok=False)
    abi = 'x86_64' if args.android else 'Linux x86_64'
    build = ROOT/'.build'/('android-x86_64' if args.android else 'audio')
    binary = build/'nh-audio-stream'
    provenance = json.loads((build/'build-provenance.json').read_text())
    if provenance.get('executables', {}).get(binary.name) != sha256(binary):
        raise ValueError('CLI provenance is stale; rebuild')
    if provenance['sdk_sha256'] != sha256(build/'libnuclear_audio.so'):
        raise ValueError('SDK provenance differs')
    lock = json.loads((ROOT/'config/audio-models.lock.json').read_text())
    descriptor = next(m for m in lock['models'] if m['id'] == args.model)
    files = [next(f for f in lock['files'] if f['path'] == path) for path in descriptor['files']]
    for item in files:
        if sha256(ROOT/item['path']) != item['sha256']:
            raise ValueError('Changed model asset')
    config = dict(vars(args), abi=abi, model_files=files, model_lock_sha256=sha256(ROOT/'config/audio-models.lock.json'),
                  manifest_sha256=sha256(ROOT/args.manifest), sdk_sha256=provenance['sdk_sha256'], cli_sha256=sha256(binary),
                  scope='standalone '+abi+' speaker SDK; fixed host ASR attribution, fresh process, OS cache retained',
                  pss_sample_interval_ms=50 if args.android else None, input_sha256={})
    record_harness(out, config)
    (out/'build-provenance.json').write_bytes((build/'build-provenance.json').read_bytes())
    (out/'config.json').write_text(json.dumps(config, indent=2))
    device = AndroidDevice(verify_app=False) if args.android else None

    def shell(*command, check=True):
        return subprocess.run(device.adb+['shell', shlex.join(list(map(str, command)))], env=device.env,
                              check=check, capture_output=True, text=True)

    def pull(remote, local):
        local.write_bytes(subprocess.check_output(device.adb+['exec-out', 'cat', remote], env=device.env))

    def upload(local, remote):
        expected = sha256(local)
        current = shell('toybox', 'sha256sum', remote, check=False)
        if current.returncode or not current.stdout.startswith(expected+' '):
            shell('mkdir', '-p', str(Path(remote).parent))
            subprocess.run(device.adb+['push', str(local), remote+'.part'], env=device.env, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            shell('mv', remote+'.part', remote)
        if shell('toybox', 'sha256sum', remote).stdout.split()[0] != expected:
            raise ValueError('Device artifact SHA mismatch: '+remote)
        return expected

    model_path = str(ROOT/files[0]['path'])
    cli_path = str(binary)
    if device:
        (out/'environment.json').write_text(json.dumps(device.metadata(), indent=2))
        base = '/data/local/tmp/nuclear-speaker-eval'
        runtime = base+'/runtime/'+sha256(binary)[:16]+'-'+provenance['sdk_sha256'][:16]
        model_dir = base+'/models/'+files[1]['sha256'][:16]
        libraries = [build/'libnuclear_audio.so', ROOT/'.tools/sherpa-android/x86_64/libsherpa-onnx-c-api.so',
                     ROOT/'.tools/sherpa-android/x86_64/libonnxruntime.so']
        libraries += sorted((ROOT/'.build/llama-android-x86_64/bin').glob('*.so'))
        config['device_runtime_sha256'] = {}
        for artifact in [binary, *libraries]:
            remote = runtime+'/'+artifact.name
            config['device_runtime_sha256'][remote] = upload(artifact, remote)
        cli_path = runtime+'/'+binary.name
        shell('chmod', '755', cli_path)
        for item in files:
            upload(ROOT/item['path'], model_dir+'/'+Path(item['path']).name)
        model_path = model_dir+'/'+Path(files[0]['path']).name
        remote_run = base+'/runs/'+args.experiment
        shell('mkdir', '-p', base+'/runs')
        shell('mkdir', remote_run)  # never overwrite an earlier device experiment
        config['remote_run'] = remote_run
    else:
        (out/'environment.json').write_text(json.dumps(dict(platform=abi, execution='standalone host CLI'), indent=2))
    (out/'config.json').write_text(json.dumps(config, indent=2))
    cases = []
    for f in map(json.loads, (ROOT/args.manifest).read_text().splitlines()):
        ident = f['audio_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', ident):
            raise ValueError('Invalid audio ID')
        source = ROOT/f['audio']
        reference = ROOT/f['reference']
        if sha256(source) != f['audio_sha256'] or sha256(reference) != f['reference_sha256']:
            raise ValueError('Changed frozen corpus')
        trace_path = ROOT/'.audio-runs'/args.baseline/ident/'transcript.json.trace.json'
        config['input_sha256'][str(trace_path.relative_to(ROOT))] = sha256(trace_path)
        trace = json.loads(trace_path.read_text())
        folder = out/ident
        folder.mkdir()
        posterior = folder/'posteriors.f32'
        samples = []
        if device:
            audio_remote = base+'/audio/'+f['audio_sha256']+source.suffix
            upload(source, audio_remote)
            result_dir = remote_run+'/'+ident
            shell('mkdir', result_dir)
            command = ['env', 'LD_LIBRARY_PATH='+runtime, cli_path, audio_remote, model_path,
                       result_dir+'/posteriors.f32', '4', '1' if args.profile == 'buffered' else '0', '600']
            # Sampling runs in the device shell; no repeated adb startup in the timed loop.
            script = device_script(command, result_dir)
            (folder/'device-command.sh').write_text(script)
            try:
                result = subprocess.run(device.adb+['shell', shlex.join(['sh', '-c', script])], env=device.env,
                                        capture_output=True, text=True, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                pid = shell('cat', result_dir+'/pid').stdout.strip()
                if pid.isdigit():
                    shell('kill', pid, check=False)
                raise
            (folder/'adb.stdout.log').write_text(result.stdout)
            (folder/'adb.stderr.log').write_text(result.stderr)
            for name in ['stdout.json', 'stderr.log', 'memory.jsonl', 'exit-code']:
                pull(result_dir+'/'+name, folder/name)
            if result.returncode or int((folder/'exit-code').read_text()):
                raise RuntimeError('Device CLI failed; private stdout/stderr retained')
            pull(result_dir+'/posteriors.f32', posterior)
            samples = list(map(json.loads, (folder/'memory.jsonl').read_text().splitlines()))
        else:
            command = [cli_path, str(source), model_path, str(posterior), '4',
                       '1' if args.profile == 'buffered' else '0', '600']
            with (folder/'stdout.json').open('w') as stdout, (folder/'stderr.log').open('w') as stderr:
                result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.timeout)
            if result.returncode:
                raise RuntimeError('Host CLI failed; private stdout/stderr retained')
        measured = json.loads((folder/'stdout.json').read_text())
        raw = np.fromfile(posterior, dtype='<f4')
        if measured['speaker_slots'] != 8 or len(raw) != measured['posterior_frames']*8:
            raise ValueError('Invalid CLI posterior dimensions')
        probs = raw.reshape(-1, 8)
        if len(probs) != measured['source_samples']//160 or not np.isfinite(probs).all() or np.any(probs < 0) or np.any(probs > 1):
            raise ValueError('Invalid CLI probability/source grid')
        if f.get('audio_seconds') is not None and abs(measured['source_samples']/16000-f['audio_seconds']) > .002:
            raise ValueError('Decoded source duration differs')
        turns = turns_from_probs(probs, measured['source_samples']/16000, resolution_ms=10)
        utterances = attribute(trace['words'], turns)
        if normalize(' '.join(t['text'] for t in utterances)) != normalize(' '.join(w['text'] for w in trace['words'])):
            raise ValueError('Attribution altered frozen ASR words')
        truth = json.loads(reference.read_text())['transcript']
        case = dict(audio_id=ident, **measured, speaker_attributed=cpwer(truth, utterances),
                    **speaker_coverage(utterances), sampled_peak_pss_kib=max((s['pss_kib'] for s in samples), default=None),
                    memory_samples=len(samples))
        if f.get('rttm'):
            case.update(diarization(truth, turns, measured['source_samples']/16000))
        if args.host_reference:
            previous = ROOT/'.audio-runs'/args.host_reference/ident
            host = json.loads((previous/'stdout.json').read_text())
            if measured['source_samples'] != host['source_samples'] or measured['decoded_pcm_sha256'] != host['decoded_pcm_sha256']:
                raise ValueError('Host/device decoded PCM differs')
            host_probs = np.fromfile(previous/'posteriors.f32', dtype='<f4').reshape(-1, 8)
            case['host_comparison'] = dict(decoded_pcm_sha256_equal=True,
                max_posterior_delta=float(abs(probs-host_probs).max(initial=0)),
                threshold_flips=int(((probs>.5)!=(host_probs>.5)).sum()))
            for artifact in [previous/'stdout.json', previous/'posteriors.f32']:
                config['input_sha256'][str(artifact.relative_to(ROOT))] = sha256(artifact)
        (folder/'trace.json').write_text(json.dumps(dict(turns=turns, utterances=utterances), indent=2))
        cases.append(case)
        print(json.dumps(case), flush=True)
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases,
                   cpwer=sum(c['speaker_attributed']['errors'] for c in cases)/sum(c['speaker_attributed']['reference_words'] for c in cases),
                   inference_rtf=sum(c['processing_seconds'] for c in cases)/sum(c['audio_seconds'] for c in cases),
                   process_peak_rss_kib=max(c['process_peak_rss_kib'] for c in cases))
    report = ROOT/'eval/results'/args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2))
        (report/name).write_bytes((out/name).read_bytes())


if __name__ == '__main__':
    main()
