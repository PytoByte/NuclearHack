#!/usr/bin/env python3
"""Cross-compile the native library for Android, without Gradle or an app."""
from pathlib import Path
import subprocess
from stamp_audio_build import stamp

ROOT = Path(__file__).resolve().parents[1]
tools = ROOT / '.tools'
cmake = ROOT / '.venv/bin/cmake'
toolchain = tools / 'ndk/build/cmake/android.toolchain.cmake'
if not toolchain.exists():
    raise SystemExit('Run make mobile-bootstrap first')
for abi in ('arm64-v8a', 'x86_64'):
    build = ROOT / '.build' / ('android-' + abi)
    command = [str(cmake), '-S', str(ROOT / 'src/audio'), '-B', str(build), '-G', 'Ninja',
               '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_TESTING=OFF',
               '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain), '-DANDROID_ABI=' + abi,
               '-DANDROID_PLATFORM=android-26', '-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON',
               '-Wno-deprecated',
               '-DNH_SHERPA_ROOT=' + str(tools / 'sherpa-host'),
               '-DNH_SHERPA_LIB_DIR=' + str(tools / 'sherpa-android' / abi),
               '-DNH_LLAMA_ROOT=' + str(ROOT / '.build' / ('llama-android-' + abi))]
    subprocess.run(command, check=True)
    subprocess.run([str(cmake), '--build', str(build), '--target', 'nuclear_audio', 'nuclear_audio_jni', 'nh-audio', '-j', '4'], check=True)
    readelf = tools / 'ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf'
    machine = 'AArch64' if abi == 'arm64-v8a' else 'Advanced Micro Devices X86-64'
    header = subprocess.check_output([str(readelf), '-h', str(build / 'libnuclear_audio.so')], text=True)
    if machine not in header:
        raise SystemExit(f'Wrong ELF machine for {abi}')
    # Check both our SDK and the vendor dependencies against the 16-KiB page requirement.
    libraries = [build / 'libnuclear_audio.so', build / 'libnuclear_audio_jni.so',
                 tools / 'sherpa-android' / abi / 'libsherpa-onnx-c-api.so',
                 tools / 'sherpa-android' / abi / 'libonnxruntime.so']
    libraries += list((ROOT / '.build' / ('llama-android-' + abi) / 'bin').glob('*.so'))
    for library in libraries:
        headers = subprocess.check_output([str(readelf), '-lW', str(library)], text=True)
        for line in headers.splitlines():
            if line.strip().startswith('LOAD') and int(line.split()[-1], 16) < 16384:
                raise SystemExit(f'LOAD alignment below 16 KiB: {library}')
    stamp(build)
    print(f'Built {abi}; execution on Android not measured', flush=True)
