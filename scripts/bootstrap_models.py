#!/usr/bin/env python3
"""Developer-only downloads of pinned weights. Never imported by the SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def fetch(url, path, expected):
    path = path.resolve()
    if not path.is_relative_to(ROOT) or path.is_relative_to(ROOT / 'task'):
        raise ValueError('Download destination must be in repository, outside task/')
    if path.exists() and sha256(path) == expected:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.part')
    print(f'Download: {path.relative_to(ROOT)}', flush=True)
    with urllib.request.urlopen(url, timeout=120) as source, temporary.open('wb') as target:
        shutil.copyfileobj(source, target)
    if sha256(temporary) != expected:
        raise ValueError(f'SHA256 mismatch: {path}')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', nargs='*', help='Model IDs; empty selects all pinned models')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'config/audio-models.lock.json').read_text())
    selected = set(args.models or [m['id'] for m in catalog['models']])
    known = {m['id'] for m in catalog['models']}
    if selected - known:
        parser.error(f'Unknown models: {selected - known}')
    paths = {p for m in catalog['models'] if m['id'] in selected for p in m['files']}
    for item in catalog['files']:
        if item['path'] in paths:
            if item.get('archive_member'):
                archive = ROOT / '.tools/downloads' / Path(item['url']).name
                fetch(item['url'], archive, item['archive_sha256'])
                path = (ROOT / item['path']).resolve()
                if not path.is_relative_to(ROOT) or path.is_relative_to(ROOT / 'task'):
                    raise ValueError('Invalid model destination')
                if path.exists() and sha256(path) == item['sha256']:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                with tarfile.open(archive) as source:
                    data = source.extractfile(item['archive_member']).read()
                if hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError('Invalid archived model file')
                path.write_bytes(data)
            else:
                fetch(item['url'], ROOT / item['path'], item['sha256'])
    print('All selected model files verified', flush=True)


if __name__ == '__main__':
    main()
