#!/usr/bin/env python3
"""Preserve exact native binaries, source snapshot and dependency hashes after a build."""
import argparse
import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from bootstrap_models import ROOT,sha256


def stamp(build):
    build=build.resolve()
    if not build.is_relative_to(ROOT/'.build'):raise ValueError('Expected repository build directory')
    android=build.name.startswith('android-')
    source=ROOT/'src/audio'
    inputs=sorted(p for p in source.rglob('*') if p.is_file() and
        (p.suffix in ('.c','.cpp','.h','.hpp') or p.name=='CMakeLists.txt') and
        (android or 'android' not in p.relative_to(source).parts))
    inputs += [ROOT/'config/audio-toolchain.lock.json']
    inputs += [ROOT/'.tools'/p for p in ('miniaudio/miniaudio.h','json/json.hpp','picosha2/picosha2.h',
        'sherpa-host/include/sherpa-onnx/c-api/c-api.h')]
    inputs += [ROOT/'third_party/llama.cpp/include/llama.h',ROOT/'third_party/llama.cpp/ggml/include/ggml.h']
    if (build/'CMakeCache.txt').exists():inputs.append(build/'CMakeCache.txt')
    sdk=build/'libnuclear_audio.so'
    if not sdk.exists():raise ValueError('Build SDK before stamping it')
    identity=dict(build_variant=build.name,sdk_sha256=sha256(sdk),inputs={str(p.relative_to(ROOT)):sha256(p) for p in inputs})
    abi=build.name.removeprefix('android-')
    runtime=[ROOT/'.tools/sherpa-android'/abi,ROOT/'.build'/('llama-android-'+abi)/'bin'] if android else [ROOT/'.tools/sherpa-host/lib',ROOT/'.build/llama-host/bin']
    libraries=list(build.glob('libnuclear_audio*.so*'))
    for directory in runtime:libraries+=list(directory.glob('*.so*'))
    identity['runtime_libraries']={str(p.relative_to(ROOT)):sha256(p) for p in libraries if p.is_file()}
    import hashlib
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    archive=ROOT/'.audio-runs/builds'/key
    archive.mkdir(parents=True,exist_ok=True)
    identity['git_sha']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    identity['git_dirty']=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT))
    identity['source_snapshot']=str((archive/'source.tar').relative_to(ROOT))
    identity['artifact_directory']=str(archive.relative_to(ROOT))
    if not (archive/'source.tar').exists():
        with tarfile.open(archive/'source.tar','w') as out:
            for p in inputs:out.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
    for p in libraries:
        destination=archive/p.name
        if destination.exists() or destination.is_symlink():continue
        if p.is_symlink():destination.symlink_to(p.readlink().name)
        else:shutil.copy2(p,destination)
    if (build/'nh-audio').exists():shutil.copy2(build/'nh-audio',archive/'nh-audio')
    data=json.dumps(identity,indent=2)+'\n'
    (archive/'provenance.json').write_text(data)
    (build/'build-provenance.json').write_text(data)
    print('Preserved native build '+key,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=ROOT/'.build/audio')
    stamp(p.parse_args().build)
