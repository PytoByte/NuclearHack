#!/usr/bin/env python3
"""Create a self-contained local model bundle; no runtime download dependency."""
import argparse
import io
import json
from pathlib import Path
import tarfile
from bootstrap_models import ROOT, sha256

def runtime_notices():
    catalog=json.loads((ROOT/'config/audio-toolchain.lock.json').read_text())
    result=[]
    for record in catalog['artifacts']:
        if record['name'].startswith('sdk-notices/'):
            path=ROOT/'.tools'/record['name']
            if sha256(path)!=record['sha256']:raise ValueError('Invalid runtime license')
            result.append((path,'licenses/'+path.name))
    for path in [ROOT/'.tools/miniaudio/LICENSE',ROOT/'.tools/json/LICENSE',ROOT/'.tools/picosha2/LICENSE',ROOT/'.tools/ndk/NOTICE']:
        if not path.exists():raise ValueError('Missing distribution notice: '+str(path))
        result.append((path,'licenses/'+path.parent.name+'-'+path.name))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/offline-models.tar')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.is_relative_to(ROOT / 'task'):
        parser.error('Bundle must be inside repository, outside task/')
    catalog = json.loads((ROOT / 'config/audio-models.lock.json').read_text())
    wanted = {'giga-v3-ctc', 'pyannote-eres2net-fp32', 'qwen3-0.6b-q8'}
    selected = [m for m in catalog['models'] if m['id'] in wanted]
    paths = {p for m in selected for p in m.get('runtime_files',m['files'])}
    files = [f for f in catalog['files'] if f['path'] in paths]
    for item in files:
        if sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError('Invalid model bundle source: ' + item['path'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w') as bundle:
        for item in files:
            bundle.add(ROOT / item['path'], arcname=item['path'], recursive=False)
        for source,name in runtime_notices():
            bundle.add(source,arcname=name,recursive=False)
        data = json.dumps(dict(models=selected, files=files), indent=2).encode()
        member = tarfile.TarInfo('model-manifest.json'); member.size = len(data)
        bundle.addfile(member, io.BytesIO(data))
    print(json.dumps(dict(bundle=str(output), bytes=output.stat().st_size, sha256=sha256(output))))


if __name__ == '__main__':
    main()
