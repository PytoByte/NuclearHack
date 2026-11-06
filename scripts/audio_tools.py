#!/usr/bin/env python3
"""Development checks, with no third-party Python dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / 'src/mobile/android'
INTERNET = 'android.permission.INTERNET'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def protected(paths):
    return [p for p in paths if p == 'task' or p.startswith('task/')]


def transcript(value):
    if not isinstance(value, dict) or set(value) != {'transcript'}:
        raise ValueError('Expected exactly {"transcript": [...]}')
    if not isinstance(value['transcript'], list):
        raise ValueError('transcript must be an array')
    previous = -1
    for i, turn in enumerate(value['transcript']):
        if not isinstance(turn, dict) or set(turn) != {'speaker_id', 'start_ms', 'end_ms', 'text'}:
            raise ValueError(f'turn {i}: wrong fields')
        if not isinstance(turn['speaker_id'], str) or not turn['speaker_id']:
            raise ValueError(f'turn {i}: invalid speaker_id')
        if not isinstance(turn['text'], str):
            raise ValueError(f'turn {i}: text must be a string')
        start, end = turn['start_ms'], turn['end_ms']
        if type(start) is not int or type(end) is not int or not 0 <= start < end:
            raise ValueError(f'turn {i}: invalid integer timestamps')
        if start < previous:
            raise ValueError(f'turn {i}: not sorted by start_ms')
        previous = start  # Overlapping speech is valid.


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def check(staged):
    paths = git('diff', '--cached', '--name-only', '-z', '--no-renames').decode().split('\0')
    if not staged:
        paths += git('diff', '--name-only', '-z', '--no-renames').decode().split('\0')
        paths += git('ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
    bad = protected(paths)
    if bad:
        raise ValueError('task/ is read-only: ' + ', '.join(bad))
    # Read the index on commit, so unstaged changes cannot hide staged permissions.
    manifests = git('ls-files', '-z', '--', 'src/**/AndroidManifest.xml').decode().split('\0')
    for name in filter(None, manifests):
        if staged:
            source = git('show', ':' + name)
        else:
            path = ROOT / name
            if not path.exists():
                continue
            source = path.read_bytes()
        manifest = ET.fromstring(source)
        for element in manifest.iter():
            if element.tag.startswith('uses-permission') and element.get(
                    '{http://schemas.android.com/apk/res/android}name') == INTERNET:
                raise ValueError(f'{name}: INTERNET permission forbidden')
    subprocess.run(['git', 'diff', '--cached' if staged else 'HEAD', '--check'], cwd=ROOT, check=True)
    print('PASS: task protection, source permissions, diff whitespace')


def doctor(android=False):
    missing = []
    names = ('git', 'python3', 'g++', 'cmake', 'ninja', 'ffmpeg')
    if android:
        names += ('java', 'adb', 'emulator', 'aapt')
    for name in names:
        found = shutil.which(name)
        print(f'{name}: {found or "MISSING"}')
        if not found:
            missing.append(name)
    print(f'host: {platform.platform()} / {platform.machine()}')
    print('Audio SDK: C++17, C ABI, CPU sherpa-onnx; no JVM/UI dependency')
    if android and shutil.which('adb'):
        subprocess.run(['adb', 'devices', '-l'], check=True, timeout=20)
    if missing:
        raise ValueError('Missing prerequisites: ' + ', '.join(missing))


def apk(path):
    if not shutil.which('aapt'):
        raise ValueError('Add Android SDK build-tools (aapt) to PATH')
    output = subprocess.check_output(['aapt', 'dump', 'permissions', str(path)], text=True)
    if INTERNET in output:
        raise ValueError('APK merged manifest requests INTERNET')
    print('PASS: APK has no INTERNET permission')


def models(manifest_path):
    manifest = load_json(manifest_path)
    entries = manifest.get('files')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Model manifest must contain nonempty files array')
    for item in entries:
        if any(not isinstance(item.get(k), str) or not item[k].strip()
               for k in ('path', 'sha256', 'source', 'version', 'license')):
            raise ValueError('Each model file needs path, sha256, source, version, license')
        path = (ROOT / item['path']).resolve()
        if not path.is_relative_to(ROOT) or path.is_relative_to(ROOT / 'task'):
            raise ValueError('Model file must be inside project, outside task/')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != item['sha256'].lower():
            raise ValueError(f'Checksum mismatch: {item["path"]}')
        print(f'PASS: {item["path"]}')


def run(command):
    if command and command[0] == '--':
        command = command[1:]
    if not command:
        raise ValueError('Provide a command after --')
    started = datetime.now(timezone.utc)
    run_id = started.strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / '.audio-runs' / run_id
    out.mkdir(parents=True, exist_ok=False)
    info = dict(run_id=run_id, started_utc=started.isoformat(), command=command,
                git_sha=git('rev-parse', 'HEAD').decode().strip(),
                git_status=git('status', '--porcelain').decode(),
                host=platform.platform(), machine=platform.machine(),
                measurement_scope='developer-host command; Android metrics not measured')
    (out / 'environment.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    print(f'Logs: {out}', flush=True)
    before = time.monotonic()
    code = 1
    try:
        with (out / 'stdout.log').open('wb') as stdout, (out / 'stderr.log').open('wb') as stderr:
            code = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr).returncode
    finally:
        (out / 'timings.json').write_text(json.dumps(dict(
            command_wall_seconds=time.monotonic() - before, exit_code=code)), encoding='utf-8')
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('doctor').add_argument('--android', action='store_true')
    commands.add_parser('hooks')
    commands.add_parser('check').add_argument('--staged', action='store_true')
    for name in ('transcript', 'apk', 'models'):
        commands.add_parser(name).add_argument('path', type=Path)
    commands.add_parser('run').add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.action == 'hooks':
            existing = subprocess.run(['git', 'config', '--get', 'core.hooksPath'],
                                      cwd=ROOT, capture_output=True, text=True).stdout.strip()
            if existing and existing != '.githooks':
                raise ValueError(f'Existing hooksPath {existing!r}; integrate hooks manually')
            legacy = ROOT / git('rev-parse', '--git-path', 'hooks/pre-commit').decode().strip()
            if not existing and legacy.exists():
                raise ValueError('Existing pre-commit hook; integrate hooks manually')
            subprocess.run(['git', 'config', '--local', 'core.hooksPath', '.githooks'], cwd=ROOT, check=True)
            print('Enabled .githooks for this checkout')
        elif args.action == 'check':
            check(args.staged)
        elif args.action == 'doctor':
            doctor(args.android)
        elif args.action == 'apk':
            apk(args.path)
        elif args.action == 'models':
            models(args.path)
        elif args.action == 'transcript':
            transcript(load_json(args.path))
            print('PASS: transcript contract')
        elif args.action == 'run':
            return run(args.command)
    except (ValueError, OSError, subprocess.SubprocessError, ET.ParseError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
