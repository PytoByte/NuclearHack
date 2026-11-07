#!/usr/bin/env python3
"""Install our debug test APK and preload/verify models on the isolated emulator."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
from bootstrap_android_audio import ROOT, environment
from bootstrap_models import sha256

PACKAGE = 'com.hexteam.audiohost'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / '.build/offline-models.tar')
    parser.add_argument('--clean', action='store_true')
    parser.add_argument('--skip-bundle', action='store_true', help='Only upload additional pinned evaluation assets')
    parser.add_argument('--model', action='append', default=[])
    parser.add_argument('--fleurs', action='store_true', help='Upload validation audio only, without references')
    args = parser.parse_args()
    env = environment()
    adb = [str(ROOT / '.tools/android-sdk/platform-tools/adb'), '-P', '5039', '-s', 'emulator-5558']
    def run(command, **kwargs): return subprocess.run(adb + command, env=env, check=True, **kwargs)
    if subprocess.check_output(adb + ['shell', 'getprop', 'ro.kernel.qemu'], env=env, text=True).strip() != '1':
        raise SystemExit('Refuse deployment outside the isolated emulator')
    if args.clean:
        subprocess.run(adb + ['uninstall', PACKAGE], env=env, capture_output=True)
    run(['install', '-r', str(ROOT / '.build/android-host/audio-sdk-host.apk')])
    def remote(command, **kwargs): return run(['shell', 'run-as ' + PACKAGE + ' sh -c ' + shlex.quote(command)], **kwargs)
    def upload(stream, relative, expected):
        destination = 'files/' + relative
        parent = str(Path(destination).parent)
        remote('mkdir -p ' + shlex.quote(parent), stdout=subprocess.DEVNULL)
        probe = subprocess.run(adb + ['shell', 'run-as ' + PACKAGE + ' toybox sha256sum ' + shlex.quote(destination)],
                               env=env, capture_output=True, text=True)
        if probe.returncode == 0 and probe.stdout.split()[0] == expected:
            print('Verified existing ' + relative, flush=True); return
        process = subprocess.Popen(adb + ['shell', 'run-as ' + PACKAGE + ' sh -c ' +
            shlex.quote('cat > ' + shlex.quote(destination))], env=env, stdin=subprocess.PIPE)
        try:
            import shutil
            shutil.copyfileobj(stream, process.stdin, 1024 * 1024)
            process.stdin.close()
            if process.wait(): raise RuntimeError('ADB upload failed')
        finally:
            if process.poll() is None: process.kill(); process.wait()
        actual = subprocess.check_output(adb + ['shell', 'run-as ' + PACKAGE + ' toybox sha256sum ' + shlex.quote(destination)],
                                         env=env, text=True).split()[0]
        if actual != expected: raise ValueError('Device checksum mismatch: ' + relative)
        print('Uploaded and verified ' + relative, flush=True)
    if not args.skip_bundle:
      with tarfile.open(args.bundle) as bundle:
        manifest = json.load(bundle.extractfile('model-manifest.json'))
        for item in manifest['files']:
            path = Path(item['path'])
            if path.is_absolute() or '..' in path.parts or path.parts[0] != 'models':
                raise ValueError('Invalid model bundle path')
            upload(bundle.extractfile(item['path']), item['path'], item['sha256'])
    catalog=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    paths={p for model in catalog['models'] if model['id'] in args.model for p in model.get('runtime_files',model['files'])}
    if set(args.model)-{m['id'] for m in catalog['models']}:raise ValueError('Unknown model ID')
    for item in catalog['files']:
        if item['path'] in paths:
            source=ROOT/item['path']
            if sha256(source)!=item['sha256']:raise ValueError('Invalid pinned model')
            with source.open('rb') as stream:upload(stream,item['path'],item['sha256'])
    if args.fleurs:
        rows=[json.loads(l) for l in (ROOT/'eval/data/fleurs-ru-validation.jsonl').read_text().splitlines()]
        for row in rows:
            source=ROOT/row['audio']
            if sha256(source)!=row['audio_sha256']:raise ValueError('Invalid FLEURS audio')
            with source.open('rb') as stream:upload(stream,'audio/fleurs/'+row['audio_id']+'.wav',row['audio_sha256'])
        data=json.dumps([r['audio_id'] for r in rows]).encode()
        upload(io.BytesIO(data),'fleurs-inputs.json',hashlib.sha256(data).hexdigest())
    for line in (ROOT / 'eval/data/dialogs-smoke.jsonl').read_text().splitlines():
        item = json.loads(line)
        source = ROOT / item['audio']
        if sha256(source) != item['audio_sha256']: raise ValueError('Invalid audio fixture')
        with source.open('rb') as stream:
            upload(stream, 'audio/' + item['audio_id'] + '.mp3', item['audio_sha256'])
    run(['shell', 'cmd', 'connectivity', 'airplane-mode', 'enable'])
    print('APK/model/audio installation complete; emulator airplane mode enabled')


if __name__ == '__main__':
    main()
