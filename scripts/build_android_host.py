#!/usr/bin/env python3
"""Build/sign the minimal offline SDK test APK using pinned SDK tools, no Gradle/UI stack."""
import os
from pathlib import Path
import subprocess
import zipfile
from bootstrap_android_audio import environment, ROOT
from package_offline_models import runtime_notices


def main():
    env = environment()
    sdk = Path(env['ANDROID_HOME'])
    tools = sdk / 'build-tools/35.0.0'
    android = sdk / 'platforms/android-35/android.jar'
    build = ROOT / '.build/android-host'
    classes = build / 'classes'; classes.mkdir(parents=True, exist_ok=True)
    dex = build / 'dex'; dex.mkdir(exist_ok=True)
    source = ROOT / 'src/audio/android'
    command = lambda args: subprocess.run([str(a) for a in args], env=env, cwd=ROOT, check=True)
    command([Path(env['JAVA_HOME']) / 'bin/javac', '-source', '8', '-target', '8', '-classpath', android,
             '-d', classes, *sorted((source / 'java').rglob('*.java'))])
    jar = build / 'classes.jar'
    command([Path(env['JAVA_HOME']) / 'bin/jar', 'cf', jar, '-C', classes, '.'])
    command([tools / 'd8', '--lib', android, '--min-api', '26', '--output', dex, jar])
    unsigned = build / 'unsigned.apk'
    command([tools / 'aapt2', 'link', '-o', unsigned, '-I', android, '--manifest', source / 'AndroidManifest.xml'])
    with zipfile.ZipFile(unsigned, 'a', compression=zipfile.ZIP_STORED) as package:
        package.write(dex / 'classes.dex', 'classes.dex')
        for source,name in runtime_notices():package.write(source,'assets/'+name)
        for abi in ('x86_64', 'arm64-v8a'):
            provenance=ROOT/'.build'/('android-'+abi)/'build-provenance.json'
            if not provenance.exists():raise RuntimeError('Build native SDK with provenance first')
            package.write(provenance,'assets/buildinfo/'+abi+'.json')
            libraries = [ROOT / '.build' / ('android-' + abi) / name for name in ('libnuclear_audio.so', 'libnuclear_audio_jni.so')]
            libraries += [ROOT / '.tools/sherpa-android' / abi / name for name in ('libsherpa-onnx-c-api.so', 'libonnxruntime.so')]
            libraries += list((ROOT / '.build' / ('llama-android-' + abi) / 'bin').glob('*.so'))
            if len(libraries) < 8:
                raise RuntimeError(f'Missing native runtime libraries for {abi}')
            for lib in libraries:
                if not lib.exists(): raise RuntimeError(f'Build mobile SDK first: {lib}')
                package.write(lib.resolve(), f'lib/{abi}/{lib.name}')
    aligned = build / 'aligned.apk'
    command([tools / 'zipalign', '-P', '16', '-f', '4', unsigned, aligned])
    key = ROOT / '.tools/android-debug.keystore'
    if not key.exists():
        command([Path(env['JAVA_HOME']) / 'bin/keytool', '-genkeypair', '-keystore', key,
            '-storepass', 'android', '-keypass', 'android', '-alias', 'androiddebugkey',
            '-dname', 'CN=Android Debug,O=Android,C=US', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000'])
    apk = build / 'audio-sdk-host.apk'
    command([tools / 'apksigner', 'sign', '--ks', key, '--ks-pass', 'pass:android', '--key-pass', 'pass:android',
             '--out', apk, aligned])
    permissions = subprocess.check_output([str(tools / 'aapt'), 'dump', 'permissions', str(apk)], env=env, text=True)
    (build / 'permissions.txt').write_text(permissions)
    if 'android.permission.INTERNET' in permissions:
        raise RuntimeError('Test APK unexpectedly requests INTERNET')
    command([tools / 'apksigner', 'verify', apk])
    print(f'Built and signed {apk}; no INTERNET permission')


if __name__ == '__main__':
    main()
