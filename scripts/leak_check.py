#!/usr/bin/env python3
"""Memory-leak gate for src/audio: cppcheck + clang-tidy + ASan/LSan + Valgrind.

Leak detection needs a Linux toolchain (MSVC ASan does not report leaks), so run
this target on the Linux host or inside WSL. Raw logs land under .audio-runs/.
"""
import argparse
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/audio'
BUILD = ROOT / '.build'
RUNS = ROOT / '.audio-runs'
MODEL_ENV = {
    'NH_VAD_MODEL': 'models/silero-vad/silero.onnx',
    'NH_SEGMENTATION_MODEL': 'models/diarization/segmentation-model.int8.onnx',
    'NH_EMBEDDING_MODEL': 'models/diarization/embedding.onnx',
    'NH_NEMOTRON_MODEL': 'models/nemotron3-diarization/model_quantized.onnx',
    'NH_ASR_ENCODER': 'models/whisper-base-int8/base-encoder.int8.onnx',
    'NH_ASR_DECODER': 'models/whisper-base-int8/base-decoder.int8.onnx',
    'NH_ASR_TOKENS': 'models/whisper-base-int8/base-tokens.txt',
}
LEAK_CHECKS = re.compile(r'clang-analyzer-(memory|cplusplus\.NewDelete|cpp\.NewDelete|Malloc|core\.Div|unix\.Malloc)')
OWNERSHIP_CHECKS = re.compile(r'(owning-memory|mismatched-new-delete|new-delete-type-mismatch| leaking)')
CHECK_NAME = re.compile(r'\[([^\]]+)\]')
VALGRIND_RE = re.compile(r'(definitely|indirectly|possibly|still) (lost|reachable): ([\d,]+) bytes in (\d+) blocks')


def tool(name, fallback=None):
    found = shutil.which(name)
    return found or fallback


def model_env():
    return {key: str(ROOT / relative) for key, relative in MODEL_ENV.items() if (ROOT / relative).is_file()}


def save(logs, name, text):
    logs.mkdir(parents=True, exist_ok=True)
    (logs / name).write_text(text, encoding='utf-8', errors='replace')


def run(logs, name, command, env=None):
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    output = result.stdout + result.stderr
    save(logs, name, output)
    return result.returncode, output


def cppcheck(logs, cppcheck_path):
    # cppcheck 2.22 exits non-zero on --enable=all information messages, so the gate
    # reads the parsed diagnostics instead of the exit code. Missing system headers
    # are suppressed: they are noise from the WSL include search, not findings.
    code, output = run(logs, 'cppcheck.txt',
                       [cppcheck_path, '--std=c++17', '--enable=all',
                        '--suppress=missingIncludeSystem', '--suppress=checkersReport', '-q', str(SOURCE)])
    findings = [line for line in output.splitlines() if ' error:' in line or ' warning:' in line]
    leaks = [line for line in findings if 'leak' in line.lower() or 'uninitialized' in line.lower()]
    return code, len(findings), leaks


def clang_tidy(logs, tidy_path, database):
    files = sorted(str(path) for path in SOURCE.rglob('*')
                   if path.suffix in {'.c', '.h', '.cpp', '.hpp'} and path.is_file()
                   and 'android' not in path.parts)
    # -p uses the CMake compile_commands.json: without it clang-tidy cannot resolve
    # headers and reports spurious "file not found" noise instead of real diagnostics.
    code, output = run(logs, 'clang-tidy.txt',
                       [tidy_path, '-quiet', '-warnings-as-errors=', '-p', str(database)] + files)
    warnings = [line for line in output.splitlines() if ': warning:' in line]
    analyzer = [line for line in warnings
                if (match := CHECK_NAME.search(line)) and 'clang-analyzer' in match[1]]
    leaks = [line for line in analyzer if LEAK_CHECKS.search(line)]
    return code, len(warnings), len(analyzer), leaks


def asan_run(logs, cmake, ctest):
    build = BUILD / 'audio-asan'
    configure = run(logs, 'asan-configure.txt',
                    [cmake, '-S', str(SOURCE), '-B', str(build), '-G', 'Ninja',
                     '-DCMAKE_BUILD_TYPE=Debug', '-DNH_SANITIZE=ON'])
    if configure[0]:
        return configure[0], 0, 'configure failed'
    build_code, build_output = run(logs, 'asan-build.txt', [cmake, '--build', str(build), '-j', '4'])
    if build_code:
        return build_code, 0, 'build failed'
    env = dict(model_env())
    code, output = run(logs, 'asan-ctest.txt', [ctest, '--test-dir', str(build), '--output-on-failure'],
                       env=env or None)
    return code, output.count(' Passed'), output


def native_build(logs, cmake):
    """Plain (unsanitized) build so Valgrind has binaries that ASan did not replace."""
    build = BUILD / 'audio'
    configure = run(logs, 'native-configure.txt',
                    [cmake, '-S', str(SOURCE), '-B', str(build), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release'])
    if configure[0]:
        return configure[0], 'configure failed'
    code, output = run(logs, 'native-build.txt', [cmake, '--build', str(build), '-j', '4'])
    return code, output


def valgrind_run(logs, valgrind_path, cycles, all_models):
    """Leak accounting under Valgrind. Valgrind interprets every ORT instruction, so
    loading all four pinned models costs minutes (measured 6m43s) versus 19s for the
    VAD path alone. By default only the VAD model is loaded here: the diarizer,
    streaming and ASR create/destroy paths are covered by the ASan/LSan ctest run,
    and the RSS plateau is measured in plain_churn. Pass --valgrind-all-models for
    the deeper pass."""
    build = BUILD / 'audio'
    binaries = [build / name for name in ('audio-c-abi-test', 'audio-merge-test', 'audio-stream-core-test',
                                          'audio-lifecycle-smoke-test')]
    binaries = [path for path in binaries if path.is_file()]
    if not binaries:
        return 1, {}

    vad_only = {key: value for key, value in model_env().items() if key == 'NH_VAD_MODEL'}
    default_env = model_env() if all_models else vad_only

    def one(path):
        env = dict(default_env)
        env['NH_LIFECYCLE_CYCLES'] = str(cycles)
        env['NH_LIFECYCLE_SECONDS'] = '1'
        result, output = run(logs, f'valgrind-{path.stem}.txt',
                             [valgrind_path, '--leak-check=full', '--show-leak-kinds=all', str(path)], env=env)
        counts = {}
        for kind, _state, bytes_, blocks in VALGRIND_RE.findall(output):
            counts[kind] = counts.get(kind, 0) + int(bytes_.replace(',', ''))
        return result, counts

    # Two at a time: each Valgrind-instrumented ORT process needs its own shadow
    # arenas, and four at once makes the WSL host swap.
    with ThreadPoolExecutor(max_workers=min(2, len(binaries))) as pool:
        runs = list(pool.map(one, binaries))
    total = {}
    for result, counts in runs:
        for kind, value in counts.items():
            total[kind] = total.get(kind, 0) + value
    return max(result for result, _ in runs), total


def plain_churn(logs, cycles):
    """Repeated create/destroy in the plain build: the test itself fails when VmRSS
    keeps growing after warm-up, which is the steady-state retention signal."""
    binary = BUILD / 'audio' / 'audio-lifecycle-smoke-test'
    if not binary.is_file():
        return 1, {}
    env = dict(model_env())
    env['NH_LIFECYCLE_CYCLES'] = str(cycles)
    code, output = run(logs, 'churn-plain.txt', [str(binary)], env=env)
    match = re.search(r'VmRSS (\d+) -> (\d+) kB \(delta (\d+)', output)
    if not match:
        return code, {}
    return code, {'rss_before_kb': int(match[1]), 'rss_after_kb': int(match[2]), 'delta_kb': int(match[3])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, default=2,
                        help='VAD create/destroy cycles under Valgrind (default 2)')
    parser.add_argument('--churn-cycles', type=int, default=30,
                        help='VAD create/destroy cycles in the plain RSS churn run (default 30)')
    parser.add_argument('--valgrind-all-models', action='store_true',
                        help='Also load diarizer/nemotron/whisper under Valgrind (minutes, not seconds)')
    parser.add_argument('--no-models', action='store_true', help='Skip pinned models in dynamic runs')
    args = parser.parse_args()

    if args.no_models:
        MODEL_ENV.clear()

    cppcheck_path = tool('cppcheck')
    tidy_path = tool('clang-tidy', str(ROOT / '.venv/bin/clang-tidy'))
    valgrind_path = tool('valgrind')
    cmake = tool('cmake', str(ROOT / '.venv/bin/cmake'))
    ctest = tool('ctest', str(ROOT / '.venv/bin/ctest'))
    missing = [name for name, path in (('cppcheck', cppcheck_path), ('clang-tidy', tidy_path),
                                       ('valgrind', valgrind_path), ('cmake', cmake), ('ctest', ctest))
               if not path]
    if missing:
        raise SystemExit('Missing leak tools: ' + ', '.join(missing) + ' (Linux host or WSL required)')

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    logs = RUNS / f'leak-{stamp}'
    results = {}

    # Static passes and the two dynamic builds share cores; Valgrind runs its binaries
    # in parallel (it is single-threaded and the slowest stage by far).
    with ThreadPoolExecutor(max_workers=4) as pool:
        native = pool.submit(native_build, logs, cmake)
        cppcheck_future = pool.submit(cppcheck, logs, cppcheck_path)

        code, findings, leaks = cppcheck_future.result()
        results['cppcheck'] = {'exit': code, 'findings': findings, 'leak_findings': len(leaks)}

        build_code, _ = native.result()
        results['native_build'] = {'exit': build_code}

        asan = pool.submit(asan_run, logs, cmake, ctest)
        churn = pool.submit(plain_churn, logs, args.churn_cycles)
        tidy = pool.submit(clang_tidy, logs, tidy_path, BUILD / 'audio')

        code, warnings, analyzer, leaks = tidy.result()
        results['clang_tidy'] = {'exit': code, 'warnings': warnings, 'clang_analyzer': analyzer,
                                 'leak_warnings': leaks}

        code, passed, _ = asan.result()
        results['asan_ctest'] = {'exit': code, 'passed_tests': passed}

        code, churn_stats = churn.result()
        results['plain_churn'] = {'exit': code, **churn_stats}

        code, lost = valgrind_run(logs, valgrind_path, args.cycles, args.valgrind_all_models)
        results['valgrind'] = {'exit': code, 'lost_bytes': lost}

    lost_total = sum(lost.get(kind, 0) for kind in ('definitely', 'indirectly', 'possibly')) if isinstance(lost, dict) else 0
    leak_free = (results['cppcheck']['findings'] == 0 and results['cppcheck']['leak_findings'] == 0
                 and results['clang_tidy']['leak_warnings'] == 0
                 and results['native_build']['exit'] == 0
                 and results['asan_ctest']['exit'] == 0 and results['asan_ctest']['passed_tests'] >= 4
                 and results['plain_churn']['exit'] == 0
                 and isinstance(lost, dict) and lost_total == 0)
    print('leak-check ' + stamp)
    for name, value in results.items():
        print(f'{name}: {value}')
    save(logs, 'summary.txt', repr(results))
    if not leak_free:
        print('FAIL: leak evidence or a failed stage; see ' + str(logs))
        return 1
    print('PASS: no leak evidence; raw logs in ' + str(logs))
    return 0


if __name__ == '__main__':
    sys.exit(main())
