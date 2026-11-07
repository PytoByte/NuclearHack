#!/usr/bin/env python3
"""Compare ASR models through the same native C ABI on the offline 4GB AVD."""
import argparse
import json
import shlex
import subprocess
import sys
import zipfile
import hashlib
from pathlib import Path
import jiwer
from native_sdk import ROOT,record_harness
from scoring import aggregate,counts,normalize,text_metrics
from compare_punctuation import summarize
from android_device import AndroidDevice
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True)
    p.add_argument('--model',required=True);p.add_argument('--threads',type=int,default=4)
    p.add_argument('--method',choices=['greedy_search','modified_beam_search'],default='greedy_search')
    p.add_argument('--language',default='ru');args=p.parse_args()
    if not args.experiment.startswith('exp_') or not args.experiment[4:].isdigit():p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    device=AndroidDevice();env=device.env;adb=device.adb;shell=device.shell
    catalog=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    model=next(m for m in catalog['models'] if m['id']==args.model)
    model_file=next(Path(f).name for f in model['files'] if Path(f).name in
        ('model.int8.onnx','model.onnx','encoder.int8.onnx','base-encoder.int8.onnx'))
    manifest=ROOT/'eval/data/fleurs-ru-validation.jsonl'
    rows={r['audio_id']:r for r in (json.loads(l) for l in manifest.read_text().splitlines())}
    config=dict(experiment_id=args.experiment,model=model,threads=args.threads,method=args.method,language=args.language,
        model_files=[f for f in catalog['files'] if f['path'] in model['files']],manifest=str(manifest.relative_to(ROOT)),manifest_sha256=sha256(manifest),
        apk_sha256=sha256(ROOT/'.build/android-host/audio-sdk-host.apk'),abi=device.abi,execution=device.execution,
        configured_ram_mib=4096,scope='Android4GB native ASR, FLEURS validation40, no dialogue/DER claim')
    record_harness(out,config)
    with zipfile.ZipFile(device.apk) as apk:
        data=apk.read('assets/buildinfo/'+device.abi+'.json');(out/'build-provenance.json').write_bytes(data)
        config['build_provenance_sha256']=hashlib.sha256(data).hexdigest()
    (out/'config.json').write_text(json.dumps(config,indent=2))
    (out/'environment.json').write_text(json.dumps(dict(build=shell('getprop','ro.build.fingerprint'),
        meminfo=shell('cat','/proc/meminfo'),cpuinfo=shell('cat','/proc/cpuinfo'),airplane_mode=True,
        git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),indent=2))
    command=adb+['shell','am','instrument','-w','-r','-e','run_id',args.experiment,'-e','model',args.model,
        '-e','family',model['family'],'-e','threads',str(args.threads),'-e','method',args.method,
        '-e','model_file',model_file,
        '-e','language',args.language,'com.hexteam.audiohost/.AsrInstrumentation']
    # ADB joins remote arguments; preserve the explicit empty autodetect value.
    command=adb+['shell',shlex.join(command[len(adb)+1:])]
    with (out/'stdout.log').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
        result=subprocess.run(command,env=env,stdout=stdout,stderr=stderr,timeout=1800)
    if result.returncode or 'INSTRUMENTATION_RESULT: result=PASS' not in (out/'stdout.log').read_text():
        subprocess.run(adb+['logcat','-d','-t','2000'],env=env,stdout=(out/'logcat.txt').open('w'))
        (out/'failure.json').write_text(json.dumps(dict(exit_code=result.returncode,stage='Android ASR')))
        raise RuntimeError('ASR instrumentation failed: '+str(out))
    def pull(name):
        b=subprocess.check_output(adb+['exec-out','run-as','com.hexteam.audiohost','cat','files/results/'+args.experiment+'/'+name],env=env)
        (out/name).write_bytes(b);return b
    measured=json.loads(pull('metrics.json'));pull('results.jsonl')
    scored=[];chars=errors=0
    for actual in measured.pop('rows'):
        row=rows[actual['audio_id']];reference=ROOT/row['reference']
        if sha256(reference)!=row['reference_sha256']:raise ValueError('Changed reference')
        truth=reference.read_text();hypothesis=actual['backend']['text']
        c=jiwer.process_characters(normalize(truth),normalize(hypothesis))
        errors+=c.substitutions+c.deletions+c.insertions;chars+=c.hits+c.substitutions+c.deletions
        scored.append(dict(audio_id=row['audio_id'],normalized=counts(truth,hypothesis),raw=counts(truth,hypothesis,False),
            audio_seconds=row['num_samples']/16000,decode_inference_ms=actual['decode_inference_ms'],text_metrics=text_metrics(truth,hypothesis)))
    seconds=sum(r['audio_seconds'] for r in scored)
    measured.update(experiment_id=args.experiment,model=args.model,threads=args.threads,audio_seconds=seconds,
        decode_inference_rtf=measured['decode_inference_ms']/1000/seconds,
        full_rtf=(measured['load_ms']+measured['decode_inference_ms'])/1000/seconds,
        normalized=aggregate([r['normalized'] for r in scored]),raw=aggregate([r['raw'] for r in scored]),
        cer=errors/chars if chars else None,scope=config['scope'],text_metrics=summarize([r['text_metrics'] for r in scored]))
    (out/'scored-metrics.json').write_text(json.dumps(measured,indent=2))
    (out/'scores.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in scored))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for source,target in [('scored-metrics.json','metrics.json'),('config.json','config.json'),('environment.json','environment.json')]:
        (report/target).write_bytes((out/source).read_bytes())
    print(json.dumps(measured,indent=2),flush=True)


if __name__=='__main__':main()
