#!/usr/bin/env python3
"""Build, align and sign an offline Android release APK."""
from __future__ import annotations

import argparse
import os
import subprocess
import zipfile
from pathlib import Path

from bootstrap_android_audio import ROOT, environment


APP = ROOT / 'src/mobile/android'
UNSIGNED = APP / 'app/build/outputs/apk/release/app-release-unsigned.apk'
DEFAULT_KEYSTORE = ROOT / '.tools/android-release.jks'
DEFAULT_STORE_PASS = "android-release"
DEFAULT_KEY_PASS = 'android-release'
DEFAULT_ALIAS = 'neuro-release'


def require_inputs():
    missing = []
    for abi in ('arm64-v8a', 'x86_64'):
        for name in ('libnuclear_audio.so', 'libnuclear_audio_jni.so'):
            if not (ROOT / '.build' / ('android-' + abi) / name).is_file():
                missing.append(f'.build/android-{abi}/{name}')
        for name in ('libsherpa-onnx-c-api.so', 'libonnxruntime.so'):
            if not (ROOT / '.tools/sherpa-android' / abi / name).is_file():
                missing.append(f'.tools/sherpa-android/{abi}/{name}')
    if missing:
        raise SystemExit('Missing release inputs:\n  ' + '\n  '.join(missing) +
                         '\nRun make mobile-build and model bootstrap first.')


def run(command, cwd=None, env=None):
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keystore', help='Release keystore path (default: local .tools/android-release.jks)')
    parser.add_argument('--alias', default=DEFAULT_ALIAS)
    parser.add_argument('--store-pass', dest='store_pass', help='Keystore password')
    parser.add_argument('--key-pass', dest='key_pass', help='Key password')
    parser.add_argument('--output', help='Signed APK destination')
    parser.add_argument('--unsigned-only', action='store_true', help='Stop after unsigned release APK')
    args = parser.parse_args()

    require_inputs()
    env = environment()
    env['JAVA_HOME'] = env['JAVA_HOME']
    gradle = APP / 'gradlew'
    run(['sh', str(gradle), ':app:assembleRelease', '-PrequireNativeAudio=true',
         '-Dorg.gradle.java.home=' + env['JAVA_HOME'], '--console=plain'],
        cwd=APP, env=env)

    if not UNSIGNED.is_file():
        raise SystemExit(f'Gradle did not produce {UNSIGNED}')

    if args.unsigned_only:
        print(f'Unsigned release APK: {UNSIGNED}')
        return

    keystore = Path(args.keystore or os.environ.get('ANDROID_KEYSTORE') or DEFAULT_KEYSTORE)
    store_pass = args.store_pass or os.environ.get('ANDROID_STORE_PASS') or DEFAULT_STORE_PASS
    key_pass = args.key_pass or os.environ.get('ANDROID_KEY_PASS') or DEFAULT_KEY_PASS
    alias = args.alias or os.environ.get('ANDROID_KEY_ALIAS') or DEFAULT_ALIAS
    output = Path(args.output or os.environ.get('ANDROID_RELEASE_APK') or (ROOT / '.build/android-app/neurostenographer-release-signed.apk'))

    if not keystore.is_file():
        if keystore == DEFAULT_KEYSTORE:
            keystore.parent.mkdir(parents=True, exist_ok=True)
            run(['keytool', '-genkeypair', '-v', '-keystore', str(keystore),
                 '-alias', alias, '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
                 '-storepass', store_pass, '-keypass', key_pass,
                 '-dname', 'CN=Neurostenographer,O=NuclearHack,C=RU'])
            print(f'Created development keystore: {keystore}')
            print('WARNING: this keystore is for local release testing only; do not use it for publishing.')
        else:
            raise SystemExit(f'Keystore not found: {keystore}')

    build_tools = Path(env['ANDROID_HOME']) / 'build-tools' / '35.0.0'
    aligned = Path('/tmp') / 'neurostenographer-release-aligned.apk'
    run([str(build_tools / 'zipalign'), '-f', '-p', '4', str(UNSIGNED), str(aligned)])
    output.parent.mkdir(parents=True, exist_ok=True)
    run([str(build_tools / 'apksigner'), 'sign', '--ks', str(keystore),
         '--ks-key-alias', alias, '--ks-pass', 'pass:' + store_pass,
         '--key-pass', 'pass:' + key_pass, '--out', str(output), str(aligned)])
    run([str(build_tools / 'apksigner'), 'verify', '--verbose', str(output)])
    with zipfile.ZipFile(output) as package:
        names = set(package.namelist())
    missing = ['lib/' + abi + '/' + name
               for abi in ('arm64-v8a', 'x86_64')
               for name in ('libnuclear_audio.so', 'libnuclear_audio_jni.so',
                            'libsherpa-onnx-c-api.so', 'libonnxruntime.so')
               if 'lib/' + abi + '/' + name not in names]
    if missing:
        raise SystemExit('Signed release APK is missing:\n  ' + '\n  '.join(missing))
    try:
        permissions = subprocess.check_output([str(build_tools / 'aapt'), 'dump', 'permissions', str(output)],
                                             env=env, text=True)
    except Exception:
        permissions = ''
    if 'android.permission.INTERNET' in permissions:
        raise SystemExit('Signed release APK merged manifest requests INTERNET')
    print(f'Signed release APK: {output} ({output.stat().st_size / (1024 * 1024):.0f} MiB)')


if __name__ == '__main__':
    main()
