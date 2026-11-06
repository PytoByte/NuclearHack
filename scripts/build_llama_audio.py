#!/usr/bin/env python3
"""Build the pinned CPU-only llama runtime, on host or Android NDK."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'cd959bae99ff4bed22bef2604f45241c09bbb8c8'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--android', choices=['arm64-v8a', 'x86_64'])
    args = parser.parse_args()
    source = ROOT / 'third_party/llama.cpp'
    if not source.exists():
        source.mkdir(parents=True)
        subprocess.run(['git', 'init', str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'remote', 'add', 'origin', 'https://github.com/ggml-org/llama.cpp.git'], check=True)
        subprocess.run(['git', '-C', str(source), 'fetch', '--depth', '1', 'origin', COMMIT], check=True)
        subprocess.run(['git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
    current = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if current != COMMIT:
        raise SystemExit('llama source revision differs; preserve checkout and review the pin')
    build = ROOT / '.build' / ('llama-android-' + args.android if args.android else 'llama-host')
    command = [str(ROOT / '.venv/bin/cmake'), '-S', str(source), '-B', str(build), '-G', 'Ninja',
        '-DCMAKE_MAKE_PROGRAM=' + str(ROOT / '.venv/bin/ninja'), '-DCMAKE_BUILD_TYPE=Release',
        '-DBUILD_SHARED_LIBS=ON', '-DGGML_NATIVE=OFF', '-DGGML_OPENMP=OFF', '-DGGML_LLAMAFILE=OFF',
        '-DGGML_CCACHE=OFF', '-DLLAMA_OPENSSL=OFF', '-DLLAMA_BUILD_COMMON=OFF',
        '-DLLAMA_BUILD_TESTS=OFF', '-DLLAMA_BUILD_EXAMPLES=OFF', '-DLLAMA_BUILD_TOOLS=OFF',
        '-DLLAMA_BUILD_APP=OFF', '-DLLAMA_BUILD_SERVER=OFF']
    if args.android:
        command += ['-DCMAKE_TOOLCHAIN_FILE=' + str(ROOT / '.tools/ndk/build/cmake/android.toolchain.cmake'),
            '-DANDROID_ABI=' + args.android, '-DANDROID_PLATFORM=android-26',
            '-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON', '-Wno-deprecated']
        if args.android == 'arm64-v8a':
            command += ['-DGGML_CPU_ARM_ARCH=armv8-a']
        else:
            # Portable emulator baseline. ISA acceleration is a later measured E22 choice.
            command += ['-DGGML_AVX=OFF', '-DGGML_AVX2=OFF', '-DGGML_FMA=OFF',
                '-DGGML_F16C=OFF', '-DGGML_BMI2=OFF', '-DGGML_SSE42=OFF']
    subprocess.run(command, check=True)
    subprocess.run([str(ROOT / '.venv/bin/cmake'), '--build', str(build), '--target', 'llama', '-j', '2'], check=True)
    print(f'Built llama CPU {args.android or "host"}: {COMMIT}', flush=True)


if __name__ == '__main__':
    main()
