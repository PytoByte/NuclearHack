#!/usr/bin/env python3
"""Extract final artifact, verify every hash, run launcher and compile/run C client."""
import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
from native_sdk import ROOT, record_harness
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True)
    p.add_argument('--bundle',default='.build/nuclear-audio-sdk-ru-v1.tar');args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    bundle=ROOT/args.bundle
    destination=ROOT/'.build'/('verify-sdk-'+args.experiment);destination.mkdir(exist_ok=False)
    config=dict(vars(args),bundle_sha256=sha256(bundle),bundle_bytes=bundle.stat().st_size,
        scope='extracted standalone SDK integrity and Linux CLI/C client execution; not Android/ARM runtime qualification')
    record_harness(out,config)
    with tarfile.open(bundle) as archive:archive.extractall(destination,filter='data')
    sdk=destination/'nuclear-audio-sdk';manifest=json.loads((sdk/'manifest.json').read_text())
    actual={str(p.relative_to(sdk)) for p in sdk.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=set(manifest['files']):raise ValueError('SDK file list differs from manifest')
    for name,digest in manifest['files'].items():
        path=sdk/name
        if not path.resolve().is_relative_to(sdk) or sha256(path)!=digest:raise ValueError('SDK content/hash mismatch')
    lib=sdk/'lib/linux-x86_64'
    env={'PATH':os.defpath,'LD_LIBRARY_PATH':str(lib)}
    def run(command,name):
        result=subprocess.run(list(map(str,command)),cwd=sdk,env=env,capture_output=True,text=True,timeout=180)
        (out/(name+'.stdout.log')).write_text(result.stdout);(out/(name+'.stderr.log')).write_text(result.stderr)
        if result.returncode:raise RuntimeError(name+' failed: '+result.stderr[-1000:])
        return result
    dependencies=run(['ldd',sdk/'bin/linux-x86_64/nh-audio'],'dependencies').stdout
    for line in dependencies.splitlines():
        if 'not found' in line:raise ValueError('Unresolved SDK dependency')
        if any(name in line for name in ['libnuclear_audio','libsherpa','libonnxruntime','libllama','libggml']):
            if str(lib) not in line:raise ValueError('Runtime escaped packaged library directory: '+line)
    fixture=json.loads((ROOT/'eval/data/dialogs-smoke.jsonl').read_text().splitlines()[0])
    if sha256(ROOT/fixture['audio'])!=fixture['audio_sha256']:raise ValueError('Changed smoke audio')
    source=ROOT/fixture['audio'];scratch=sdk/'scratch';scratch.mkdir()
    output=sdk/'launcher-transcript.json'
    run([sdk/'run-linux.sh',source,output,scratch],'launcher')
    expected=json.loads((ROOT/'.audio-runs/exp_0237'/fixture['audio_id']/'transcript.json').read_text())
    if json.loads(output.read_text())!=expected:raise ValueError('Packaged CLI changed transcript')
    client=sdk/'example-client'
    run(['cc','-std=c11','-Wall','-Wextra','-Werror',sdk/'examples/transcribe_file.c','-I'+str(sdk/'include'),
        '-L'+str(lib),'-lnuclear_audio','-Wl,-rpath-link,'+str(lib),'-Wl,-rpath,$ORIGIN/lib/linux-x86_64','-o',client],'compile-client')
    client_output=sdk/'client-transcript.json'
    run([client,source,client_output,sdk/'models/giga-v3-ctc-punct/model.int8.onnx',sdk/'models/giga-v3-ctc-punct/tokens.txt',
        sdk/'models/nemotron3-diarization/model_quantized.onnx',scratch],'c-client')
    if json.loads(client_output.read_text())!=expected:raise ValueError('Packaged C client changed transcript')
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],bundle_sha256=config['bundle_sha256'],bundle_bytes=config['bundle_bytes'],
        manifest_verified_files=len(manifest['files']),runtime_resolved_inside_bundle=True,
        launcher_json_exact=True,c_client_compiled=True,c_client_default_config_json_exact=True,passed=True,
        limitation='Linux extracted-package execution; native Android libs are included/cross-built, not physical ARM tested. No raw fixtures/research Python/Qwen weights shipped.')
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name,value in [('config.json',config),('metrics.json',metrics)]:
        (out/name).write_text(json.dumps(value,indent=2));(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics),flush=True)


if __name__=='__main__':main()
