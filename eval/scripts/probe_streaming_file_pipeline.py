#!/usr/bin/env python3
"""Run the complete new public file API: actual ASR -> streaming speaker -> JSON.

All target stages run on the AVD; host ASR words are never substituted. The
optional frozen prototype comparison is a qualification check, not inference.
"""
import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from native_sdk import ROOT, record_harness
from android_device import AndroidDevice
from probe_stream_cli import device_script
from run_file_pipeline import profile, cpwer
from probe_reclustering import diarization
from scoring import text_metrics, speaker_coverage
from compare_punctuation import summarize
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256
from audio_tools import transcript as validate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True)
    p.add_argument('--manifest', default='eval/data/dialogs-smoke.jsonl')
    p.add_argument('--baseline', default='exp_0125')
    p.add_argument('--model', choices=['giga-v3-ctc', 'giga-v3-ctc-punct'], default='giga-v3-ctc')
    p.add_argument('--prototype', help='exp_0190 for six natural posterior-anchor variants')
    p.add_argument('--android', action='store_true')
    p.add_argument('--entry-point', choices=['stream', 'final'], default='stream')
    p.add_argument('--require-word-parity', action='store_true')
    p.add_argument('--asan', action='store_true', help='Real-model host sanitizer check; timings are diagnostic')
    p.add_argument('--host-reference')
    p.add_argument('--timeout', type=int, default=1200)
    args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment): p.error('Use exp_NNNN')
    if args.asan and args.android: p.error('ASan probe is host-only')
    if args.model != 'giga-v3-ctc' and args.prototype:
        p.error('Frozen prototype slots require the original GigaAM words')
    out = ROOT/'.audio-runs'/args.experiment; out.mkdir(parents=True, exist_ok=False)
    build = ROOT/'.build'/('android-x86_64' if args.android else ('audio-asan' if args.asan else 'audio'))
    binary = build/'nh-audio'
    provenance = json.loads((build/'build-provenance.json').read_text())
    if provenance['sdk_sha256'] != sha256(build/'libnuclear_audio.so') or provenance['executables']['nh-audio'] != sha256(binary):
        raise ValueError('Stale SDK/CLI build provenance')
    for path, digest in provenance['inputs'].items():
        if path.startswith('src/audio/') and sha256(ROOT/path) != digest:
            raise ValueError('Native source changed since build: '+path)
    lock = json.loads((ROOT/'config/audio-models.lock.json').read_text())
    spk = next(m for m in lock['models'] if m['id'] == 'nemotron3-diarization-q8')
    asr = next(m for m in lock['models'] if m['id'] == args.model)
    asr_paths = asr.get('runtime_files', asr['files'])
    paths = [next(p for p in asr_paths if Path(p).name == 'model.int8.onnx'),
             next(p for p in asr['files'] if Path(p).name == 'tokens.txt'), *spk['files']]
    files = [next(f for f in lock['files'] if f['path'] == path) for path in paths]
    for f in files:
        if sha256(ROOT/f['path']) != f['sha256']: raise ValueError('Changed model: '+f['path'])
    config = dict(vars(args), abi='x86_64 AVD4096MiB' if args.android else 'Linux x86_64',
        model_files=files, model_lock_sha256=sha256(ROOT/'config/audio-models.lock.json'),
        manifest_sha256=sha256(ROOT/args.manifest), sdk_sha256=provenance['sdk_sha256'],
        cli_sha256=sha256(binary), threads=4, profile=1, word_anchor_ms=160,
        scope='full native '+args.model+' -> streaming Q8 posterior word merge -> strict JSON; '+('x86 AVD, not ARM' if args.android else ('host ASan/UBSan diagnostic, not performance' if args.asan else 'host')), input_sha256={})
    record_harness(out, config)
    (out/'build-provenance.json').write_bytes((build/'build-provenance.json').read_bytes())
    (out/'config.json').write_text(json.dumps(config, indent=2))
    device = AndroidDevice(verify_app=False) if args.android else None
    def shell(*cmd, check=True):
        return subprocess.run(device.adb+['shell', shlex.join(list(map(str, cmd)))], env=device.env, check=check, capture_output=True, text=True)
    def pull(remote, local): local.write_bytes(subprocess.check_output(device.adb+['exec-out', 'cat', remote], env=device.env))
    def upload(local, remote):
        digest = sha256(local); previous = shell('toybox', 'sha256sum', remote, check=False)
        if previous.returncode or not previous.stdout.startswith(digest+' '):
            shell('mkdir', '-p', str(Path(remote).parent))
            subprocess.run(device.adb+['push', str(local), remote+'.part'], env=device.env, check=True, capture_output=True)
            shell('mv', remote+'.part', remote)
        if shell('toybox', 'sha256sum', remote).stdout.split()[0] != digest: raise ValueError('Device asset changed')
        return digest
    models = [str(ROOT/path) for path in paths]
    cli = str(binary)
    if device:
        (out/'environment.json').write_text(json.dumps(device.metadata(), indent=2))
        base = '/data/local/tmp/nuclear-file-stream-eval'
        runtime = base+'/runtime/'+sha256(binary)[:16]+'-'+provenance['sdk_sha256'][:16]
        libraries = [build/'libnuclear_audio.so', ROOT/'.tools/sherpa-android/x86_64/libsherpa-onnx-c-api.so', ROOT/'.tools/sherpa-android/x86_64/libonnxruntime.so']
        libraries += sorted((ROOT/'.build/llama-android-x86_64/bin').glob('*.so'))
        config['device_runtime_sha256'] = {runtime+'/'+a.name:upload(a, runtime+'/'+a.name) for a in [binary, *libraries]}
        cli = runtime+'/nh-audio'; shell('chmod', '755', cli)
        models = []
        for f in files:
            remote = base+'/models/'+f['sha256'][:16]+'/'+Path(f['path']).name
            # ONNX graph + external data must retain their sibling relationship.
            if f['path'].startswith('models/nemotron3-diarization/'):
                remote = base+'/models/'+files[3]['sha256'][:16]+'/'+Path(f['path']).name
            upload(ROOT/f['path'], remote); models.append(remote)
        remote_run = base+'/runs/'+args.experiment
        shell('mkdir', '-p', base+'/runs'); shell('mkdir', remote_run)
        config['remote_run'] = remote_run
    (out/'config.json').write_text(json.dumps(config, indent=2))
    command_name = 'transcribe-final' if args.entry_point == 'final' else 'transcribe-stream'
    command_options = ['4', '600'] if args.entry_point == 'final' else ['4', '1', '20', '600']
    cases = []
    for f in map(json.loads, (ROOT/args.manifest).read_text().splitlines()):
        ident = f['audio_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', ident): raise ValueError('Invalid audio ID')
        for field in ['audio', 'reference']:
            if sha256(ROOT/f[field]) != f[field+'_sha256']: raise ValueError('Changed fixture')
        folder = out/ident; folder.mkdir()
        output = folder/'transcript.json'
        if device:
            audio = base+'/audio/'+f['audio_sha256']+Path(f['audio']).suffix
            upload(ROOT/f['audio'], audio)
            result_dir = remote_run+'/'+ident; shell('mkdir', result_dir)
            target_output = result_dir+'/transcript.json'
            command = ['env', 'LD_LIBRARY_PATH='+runtime, cli, command_name, audio, target_output,
                       models[0], models[1], models[2], result_dir, *command_options]
            script = device_script(command, result_dir)
            (folder/'device-command.sh').write_text(script)
            began = time.perf_counter()
            try:
                result = subprocess.run(device.adb+['shell', shlex.join(['sh', '-c', script])], env=device.env,
                    text=True, capture_output=True, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                pid = shell('cat', result_dir+'/pid').stdout.strip()
                if pid.isdigit(): shell('kill', pid, check=False)
                raise
            outer = time.perf_counter()-began
            for name in ['stdout.json', 'stderr.log', 'memory.jsonl', 'exit-code']:
                pull(result_dir+'/'+name, folder/name)
            if result.returncode or int((folder/'exit-code').read_text()): raise RuntimeError('Target file API failed; logs retained')
            pull(target_output, output); pull(target_output+'.trace.json', folder/'transcript.json.trace.json')
            samples = list(map(json.loads, (folder/'memory.jsonl').read_text().splitlines()))
            measured = json.loads((folder/'stdout.json').read_text())
            timing = dict(wall_seconds=measured['processing_seconds'], outer_adb_wall_seconds=outer,
                process_peak_rss_kib=measured['process_peak_rss_kib'], exit_code=0,
                sampled_peak_pss_kib=max(s['pss_kib'] for s in samples), memory_samples=len(samples))
        else:
            command = [cli, command_name, str(ROOT/f['audio']), str(output), models[0], models[1], models[2], str(folder), *command_options]
            (folder/'command.json').write_text(json.dumps(command, indent=2))
            timing = profile(command, folder)
            if timing['exit_code']: raise RuntimeError('Native full file API failed; stderr retained')
            measured = json.loads((folder/'stdout.log').read_text())
        duration = measured['source_samples']/16000
        if f.get('audio_seconds') is not None and abs(duration-f['audio_seconds']) > .002: raise ValueError('Decoded source duration differs')
        actual = json.loads(output.read_text()); validate(actual)
        trace = json.loads((folder/'transcript.json.trace.json').read_text())
        reference_path = ROOT/'.audio-runs'/args.baseline/ident/'transcript.json.trace.json'
        config['input_sha256'][str(reference_path.relative_to(ROOT))] = sha256(reference_path)
        old = json.loads(reference_path.read_text())
        truth = json.loads((ROOT/f['reference']).read_text())['transcript']
        same_words = trace['words'] == old['words']
        case = dict(audio_id=ident, **timing, audio_seconds=duration, source_samples=measured['source_samples'],
            decoded_pcm_sha256=trace['decoded_pcm_sha256'], full_rtf=timing['wall_seconds']/duration,
            native_stream=trace['speaker_stream'], baseline_words_exact=same_words,
            text_metrics=text_metrics(' '.join(t['text'] for t in truth), ' '.join(t['text'] for t in actual['transcript'])),
            speaker_attributed=cpwer(truth, actual['transcript']), **speaker_coverage(actual['transcript']), json_valid=True)
        if not args.android and (args.model == 'giga-v3-ctc' or args.require_word_parity) and not same_words: raise ValueError('New host file backend changed frozen ASR words/times')
        if args.prototype:
            expected_path = ROOT/'.audio-runs'/args.prototype/(ident+'.variants.json')
            config['input_sha256'][str(expected_path.relative_to(ROOT))] = sha256(expected_path)
            expected = json.loads(expected_path.read_text())['posterior_first_160ms']
            slots = [int(w['speaker_id'].split('_')[1]) for w in expected]
            case['prototype_slots_exact'] = trace['word_speaker_slots'] == slots
            if not args.android and not case['prototype_slots_exact']: raise ValueError('Native posterior merge differs from validated prototype')
        if f.get('rttm'):
            turns = [dict(speaker_id='slot_'+str(t['speaker']), start_ms=t['start_ms'], end_ms=t['end_ms']) for t in trace['speaker_turns']]
            case.update(diarization(truth, turns, duration))
        if args.host_reference:
            host_dir = ROOT/'.audio-runs'/args.host_reference/ident
            host = json.loads((host_dir/'transcript.json.trace.json').read_text())
            for path in [host_dir/'transcript.json.trace.json', host_dir/'transcript.json']:
                config['input_sha256'][str(path.relative_to(ROOT))] = sha256(path)
            case['host_comparison'] = dict(source_pcm_exact=trace['decoded_pcm_sha256']==host['decoded_pcm_sha256'],
                words_exact=trace['words']==host['words'], raw_turns_exact=trace['speaker_turns']==host['speaker_turns'])
            if not case['host_comparison']['source_pcm_exact']: raise ValueError('Actual host/AVD PCM differs')
        cases.append(case); print(json.dumps(dict(audio_id=ident, full_rtf=case['full_rtf'], cpwer=case['speaker_attributed']['cpwer'])), flush=True)
    text = summarize([c['text_metrics'] for c in cases])
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases, text_metrics=text, normalized=text['normalized'],
        cer=text['normalized_cer']['cer'], cpwer=sum(c['speaker_attributed']['errors'] for c in cases)/sum(c['speaker_attributed']['reference_words'] for c in cases),
        inference_rtf=sum(c['wall_seconds'] for c in cases)/sum(c['audio_seconds'] for c in cases), process_peak_rss_kib=max(c['process_peak_rss_kib'] for c in cases))
    report = ROOT/'eval/results'/args.experiment; report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2)); (report/name).write_bytes((out/name).read_bytes())


if __name__ == '__main__': main()
