#!/usr/bin/env python3
"""Assemble the selected SDK, native runtimes and models; no research dependencies."""
import argparse
import io
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from bootstrap_models import ROOT, sha256
from package_offline_models import runtime_notices


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.build/nuclear-audio-sdk-ru-v1.tar')
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'.build'):parser.error('SDK artifact must be inside .build/')
    preset=json.loads((ROOT/'config/audio-sdk-preset.json').read_text())
    lock=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    selected=[m for m in lock['models'] if m['id'] in [preset['asr'],preset['diarization']]]
    if len(selected)!=2:raise ValueError('Missing selected models')
    paths={p for m in selected for p in m.get('runtime_files',m['files'])}
    files=[f for f in lock['files'] if f['path'] in paths]
    if len(files)!=len(paths):raise ValueError('Unpinned SDK models')
    entries={}
    def add(path,name):
        if name in entries:raise ValueError('Duplicate SDK path '+name)
        if not Path(path).is_file():raise ValueError('Missing SDK input '+str(path))
        if Path(path).is_symlink() and (Path(path).readlink().is_absolute() or not Path(path).resolve().is_relative_to(Path(path).parent.resolve())):
            raise ValueError('Runtime symlink must resolve beside its packaged library')
        entries[name]=Path(path)
    for item in files:
        if sha256(ROOT/item['path'])!=item['sha256']:raise ValueError('Changed model')
        add(ROOT/item['path'],item['path'])
    for abi,build,runtime,llama in [
      ('linux-x86_64','audio','.tools/sherpa-host/lib','llama-host'),
      ('android-arm64-v8a','android-arm64-v8a','.tools/sherpa-android/arm64-v8a','llama-android-arm64-v8a'),
      ('android-x86_64','android-x86_64','.tools/sherpa-android/x86_64','llama-android-x86_64')]:
        directory=ROOT/'.build'/build
        stamp=json.loads((directory/'build-provenance.json').read_text())
        if sha256(directory/'libnuclear_audio.so')!=stamp['sdk_sha256']:raise ValueError('Stale SDK provenance')
        for name,digest in stamp['executables'].items():
            if sha256(directory/name)!=digest:raise ValueError('Stale CLI provenance')
        for path,digest in stamp['inputs'].items():
            if path.startswith('src/audio/') and sha256(ROOT/path)!=digest:raise ValueError('Native source changed since qualification')
        for path,digest in stamp['runtime_libraries'].items():
            if sha256(ROOT/path)!=digest:raise ValueError('Runtime differs from qualified build '+path)
        for path in sorted(directory.glob('libnuclear_audio.so*')):add(path,'lib/'+abi+'/'+path.name)
        for name in ['libsherpa-onnx-c-api.so','libonnxruntime.so']:add(ROOT/runtime/name,'lib/'+abi+'/'+name)
        for path in sorted((ROOT/'.build'/llama/'bin').glob('*.so*')):add(path,'lib/'+abi+'/'+path.name)
        add(directory/'nh-audio','bin/'+abi+'/nh-audio')
        add(directory/'build-provenance.json','provenance/'+abi+'.json')
    for source,name in runtime_notices():add(source,name)
    if (ROOT/'third_party/llama.cpp/LICENSE').exists():
        add(ROOT/'third_party/llama.cpp/LICENSE','licenses/llama-LICENSE')
    for source,name in [
      ('src/audio/include/nuclear_audio.h','include/nuclear_audio.h'),
      ('src/audio/examples/transcribe_file.c','examples/transcribe_file.c'),
      ('config/audio-sdk-preset.json','preset.json'),
      ('docs/ARCHITECTURE.md','docs/ARCHITECTURE.md'),
      ('docs/RESEARCH.md','docs/RESEARCH.md')]:add(ROOT/source,name)
    manifest=dict(preset=preset,models=selected,model_files=files,
        files={name:sha256(path) for name,path in sorted(entries.items())},
        source_git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        note='Native build hashes/provenance identify measured binaries; preset/docs/examples may be newer. Android ARM cross-build is not runtime qualification. Summary weights not included.')
    asr=next(p for p in paths if p.endswith('model.int8.onnx'));tokens=next(p for p in paths if p.endswith('tokens.txt'))
    speaker=next(p for p in paths if p.endswith('model_quantized.onnx'))
    launcher='''#!/bin/sh
set -eu
if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo 'Usage: run-linux.sh INPUT OUTPUT SCRATCH [CHECKPOINT_DIRECTORY]' >&2
  exit 1
fi
NH_SDK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export LD_LIBRARY_PATH="$NH_SDK_DIR/lib/linux-x86_64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$NH_SDK_DIR/bin/linux-x86_64/nh-audio" transcribe-final "$1" "$2" \\
  "$NH_SDK_DIR/ASR_PATH" "$NH_SDK_DIR/TOKENS_PATH" \\
  "$NH_SDK_DIR/SPEAKER_PATH" "$3" 4 600 "${4:--}"
'''.replace('ASR_PATH',asr).replace('TOKENS_PATH',tokens).replace('SPEAKER_PATH',speaker)
    generated={
        'run-linux.sh':(launcher.encode(),0o755),
        'README.md':((ROOT/'src/audio/README.md').read_text().replace('../../docs/','docs/').encode(),0o644),
    }
    manifest['files'].update({name:hashlib.sha256(data).hexdigest() for name,(data,_) in generated.items()})
    generated['manifest.json']=(json.dumps(manifest,indent=2).encode(),0o644)
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix(output.suffix+'.part')
    with tarfile.open(temporary,'w',dereference=False) as archive:
        for name,path in sorted(entries.items()):archive.add(path,arcname='nuclear-audio-sdk/'+name,recursive=False)
        for name,(data,mode) in generated.items():
            member=tarfile.TarInfo('nuclear-audio-sdk/'+name);member.size=len(data);member.mode=mode;archive.addfile(member,io.BytesIO(data))

    temporary.replace(output)
    print(json.dumps(dict(bundle=str(output),bytes=output.stat().st_size,sha256=sha256(output),preset=preset['id'])))


if __name__=='__main__':main()
