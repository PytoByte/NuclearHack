#!/usr/bin/env python3
"""Install pinned native dependencies locally, without sudo or Android UI tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.tools'


def digest(path, algorithm):
    value = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(data)
    return value.hexdigest()


def install(item):
    destination = TOOLS / item['name']
    checksum = item.get('sha256') or item['sha1']
    algorithm = 'sha256' if 'sha256' in item else 'sha1'
    marker = destination / '.artifact-checksum' if item.get('archive') else None
    if marker and marker.exists() and marker.read_text() == checksum:
        return
    if not marker and destination.exists() and digest(destination, algorithm) == checksum:
        return
    archive = TOOLS / 'downloads' / Path(item['url']).name
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() or digest(archive, algorithm) != checksum:
        temporary = archive.with_suffix(archive.suffix + '.part')
        print(f'Downloading {item["name"]}', flush=True)
        with urllib.request.urlopen(item['url'], timeout=120) as response, temporary.open('wb') as target:
            shutil.copyfileobj(response, target)
        if digest(temporary, algorithm) != checksum:
            raise RuntimeError(f'Checksum mismatch: {item["name"]}')
        temporary.replace(archive)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not marker:
        shutil.copyfile(archive, destination)
        return
    with tempfile.TemporaryDirectory(dir=TOOLS) as temp:
        unpacked = Path(temp)
        if item['archive'] == 'tar':
            with tarfile.open(archive) as source:
                source.extractall(unpacked, filter='data')
        else:
            with zipfile.ZipFile(archive) as source:
                # Restore executable bits required by clang/LLVM in the NDK.
                for entry in source.infolist():
                    path = (unpacked / entry.filename).resolve()
                    if not path.is_relative_to(unpacked.resolve()):
                        raise RuntimeError('Invalid archive path')
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        link = source.read(entry).decode('utf-8')
                        if not (path.parent / link).resolve().is_relative_to(unpacked.resolve()):
                            raise RuntimeError('Invalid archive symlink')
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.symlink_to(link)
                        continue
                    source.extract(entry, unpacked)
                    mode = (entry.external_attr >> 16) & 0o777
                    if mode:
                        path.chmod(mode)
        content = next(unpacked.iterdir()) if item.get('strip') else unpacked
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(content, destination, symlinks=True)
        marker.write_text(checksum)
    print(f'Installed {item["name"]}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--android', action='store_true', help='Also install pinned NDK (~664 MB download)')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('This toolchain lock targets Linux x86_64 hosts')
    lock = json.loads((ROOT / 'config/audio-toolchain.lock.json').read_text())
    for item in lock['artifacts']:
        if not item.get('optional') or args.android:
            install(item)
    python = ROOT / '.venv/bin/python'
    ffmpeg = subprocess.check_output([str(python), '-c',
        'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'], text=True).strip()
    (TOOLS / 'bin').mkdir(exist_ok=True)
    link = TOOLS / 'bin/ffmpeg'
    if link.is_symlink():
        link.unlink()
    if not link.exists():
        link.symlink_to(ffmpeg)
    print('Ready. Source scripts/audio-env.sh or use make native-test.')


if __name__ == '__main__':
    main()
