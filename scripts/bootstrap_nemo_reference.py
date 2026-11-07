#!/usr/bin/env python3
"""Install the pinned official CPU reference; never part of the shipped SDK."""
import hashlib
import json
import tarfile
from pathlib import Path
from bootstrap_audio import ROOT, TOOLS, install
from bootstrap_models import sha256, fetch


def main():
    spec = next(a for a in json.loads((ROOT/'config/audio-toolchain.lock.json').read_text())['research_artifacts']
                if a['name'] == 'nemo-reference/0.3.0')
    archive = TOOLS/'downloads'/Path(spec['url']).name
    fetch(spec['url'], archive, spec['sha256'])
    install(spec)
    directory = TOOLS/spec['name']
    def matches_archive():
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                relative = Path(*Path(member.name).parts[1:])
                if not relative.parts: continue
                path = directory/relative
                if member.isfile():
                    expected = hashlib.file_digest(source.extractfile(member), 'sha256').hexdigest()
                    if not path.is_file() or sha256(path) != expected: return False
                elif member.issym():
                    if not path.is_symlink() or str(path.readlink()) != member.linkname: return False
        return True
    if not matches_archive():
        (directory/'.artifact-checksum').unlink(missing_ok=True)
        install(spec)
        if not matches_archive(): raise RuntimeError('Installed reference differs from verified release archive')
    files = {str(p.relative_to(directory)): sha256(p) for p in sorted(directory.rglob('*'))
             if p.is_file() and p.name not in ['.artifact-checksum', 'reference-provenance.json']}
    (directory/'reference-provenance.json').write_text(json.dumps(dict(artifact=spec, files=files), indent=2)+'\n')
    print('Verified official runtime archive and recorded installed file hashes')


if __name__ == '__main__':
    main()
