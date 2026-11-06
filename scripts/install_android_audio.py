#!/usr/bin/env python3
"""Install our debug test APK and preload/verify models on the isolated emulator."""
import argparse
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
    with tarfile.open(args.bundle) as bundle:
        manifest = json.load(bundle.extractfile('model-manifest.json'))
        for item in manifest['files']:
            path = Path(item['path'])
            if path.is_absolute() or '..' in path.parts or path.parts[0] != 'models':
                raise ValueError('Invalid model bundle path')
            upload(bundle.extractfile(item['path']), item['path'], item['sha256'])
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
