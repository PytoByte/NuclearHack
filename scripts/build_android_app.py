#!/usr/bin/env python3
"""Build the Compose Android app with the local native SDK and pinned models."""
from pathlib import Path
import shutil
import subprocess
import zipfile
from bootstrap_android_audio import environment, ROOT

APP = ROOT / 'src/mobile/android'
APK = APP / 'app/build/outputs/apk/debug/app-debug.apk'
OUTPUT = ROOT / '.build/android-app/neurostenographer-debug.apk'
ABIS = ('arm64-v8a', 'x86_64')
NATIVE_NAMES = ('libnuclear_audio.so', 'libnuclear_audio_jni.so',
                'libsherpa-onnx-c-api.so', 'libonnxruntime.so')
REQUIRED_MODELS = (
    'models/giga-v3-ctc/model.int8.onnx',
    'models/giga-v3-ctc/tokens.txt',
    'models/diarization/segmentation-model.onnx',
    'models/diarization/embedding.onnx',
)
OPTIONAL_MODELS = (
    'models/giga-v3-ctc-punct/model.int8.onnx',
    'models/nemotron3-diarization/model_quantized.onnx',
    'models/qwen3-0.6b-q8/Qwen3-0.6B-Q8_0.gguf',
)


def native_libraries(abi):
    return [ROOT / '.build' / ('android-' + abi) / name for name in NATIVE_NAMES[:2]] + [
        ROOT / '.tools/sherpa-android' / abi / name for name in NATIVE_NAMES[2:]]


def require_inputs():
    missing = [str(path.relative_to(ROOT)) for path in
               [*(ROOT / name for name in REQUIRED_MODELS),
                *(library for abi in ABIS for library in native_libraries(abi))]
               if not path.is_file()]
    if missing:
        raise SystemExit('Missing app inputs:\n  ' + '\n  '.join(missing) +
                         '\nRun make mobile-build and scripts/bootstrap_models.py first.')


def verify_package():
    with zipfile.ZipFile(OUTPUT) as package:
        names = set(package.namelist())
    missing = [f'lib/{abi}/{name}' for abi in ABIS for name in NATIVE_NAMES
               if f'lib/{abi}/{name}' not in names]
    missing += ['assets/' + name for name in REQUIRED_MODELS
                if 'assets/' + name not in names]
    if missing:
        raise RuntimeError('APK is missing:\n  ' + '\n  '.join(missing))
    env = environment()
    aapt = Path(env['ANDROID_HOME']) / 'build-tools/35.0.0/aapt'
    permissions = subprocess.check_output([str(aapt), 'dump', 'permissions', str(OUTPUT)],
                                          env=env, text=True)
    (OUTPUT.parent / 'permissions.txt').write_text(permissions)
    if 'android.permission.INTERNET' in permissions:
        raise RuntimeError('APK merged manifest requests INTERNET')


def main():
    require_inputs()
    env = environment()
    subprocess.run(['sh', 'gradlew', ':app:assembleDebug', '-PrequireNativeAudio=true',
                    '-Dorg.gradle.java.home=' + env['JAVA_HOME'], '--console=plain'],
                   cwd=APP, env=env, check=True)
    if not APK.is_file():
        raise SystemExit(f'Gradle did not produce {APK}')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(APK, OUTPUT)
    verify_package()
    for name in OPTIONAL_MODELS:
        if not (ROOT / name).is_file():
            print(f'Optional model absent: {name}')
    size = OUTPUT.stat().st_size / (1024 * 1024)
    print(f'Built {OUTPUT} ({size:.0f} MiB); native libs and models packaged; no INTERNET permission')


if __name__ == '__main__':
    main()
