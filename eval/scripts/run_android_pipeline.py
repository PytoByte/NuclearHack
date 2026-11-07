#!/usr/bin/env python3
"""Execute the configurable C ABI file pipeline on the verified offline 4GB AVD."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shlex
import subprocess
import sys
import zipfile
from native_sdk import ROOT,record_harness
from android_device import AndroidDevice,PACKAGE
from scoring import aggregate,counts
from run_file_pipeline import cpwer
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256
from audio_tools import transcript as validate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True)
    p.add_argument('--threads',type=int,default=4);p.add_argument('--threshold',type=float,default=.8)
    p.add_argument('--chunk-seconds',type=int,default=20);p.add_argument('--max-seconds',type=int,default=600)
    p.add_argument('--summary',action='store_true');p.add_argument('--checkpoint',action='store_true')
    p.add_argument('--model',default='giga-v3-ctc');p.add_argument('--embedding',default='embedding.onnx')
    p.add_argument('--quant',choices=['fp32','int8'],default='fp32')
    p.add_argument('--min-on',type=float,default=.3);p.add_argument('--min-off',type=float,default=.5)
    p.add_argument('--window-shift-ratio',type=float,default=.1)
    p.add_argument('--attribution',choices=['overlap','midpoint'],default='overlap')
    p.add_argument('--manifest',type=Path,default=ROOT/'eval/data/dialogs-smoke.jsonl')
    p.add_argument('--cases',help='Comma-separated IDs; empty selects full manifest')
    p.add_argument('--cancel-stage');p.add_argument('--cancel-after-frames',type=int,default=0)
    p.add_argument('--expect-cancel',action='store_true');p.add_argument('--timeout',type=int,default=9000)
    args=p.parse_args()
    if not args.experiment.startswith('exp_') or not args.experiment[4:].isdigit():p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    device=AndroidDevice();catalog=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    model=next(m for m in catalog['models'] if m['id']==args.model)
    if model['family']!='ctc':p.error('File pipeline supports CTC; use ASR API for RNNT/Whisper')
    model_file=next(Path(f).name for f in model.get('runtime_files',model['files']) if Path(f).name in ('model.int8.onnx','model.onnx'))
    manifest=args.manifest.resolve();fixtures={r['audio_id']:r for r in (json.loads(l) for l in manifest.read_text().splitlines())}
    selected=args.cases.split(',') if args.cases else list(fixtures)
    if any(i not in fixtures for i in selected):p.error('Unknown audio ID')
    config=dict(vars(args));config.update(manifest=str(manifest.relative_to(ROOT)),manifest_sha256=sha256(manifest),
        abi=device.abi,avd_configured_ram_mib=4096,apk_sha256=device.apk_sha256,
        model_lock_sha256=sha256(ROOT/'config/audio-models.lock.json'),selected_audio_ids=selected)
    record_harness(out,config)
    with zipfile.ZipFile(device.apk) as apk:
        data=apk.read('assets/buildinfo/'+device.abi+'.json');(out/'build-provenance.json').write_bytes(data)
        config['build_provenance_sha256']=hashlib.sha256(data).hexdigest()
    (out/'config.json').write_text(json.dumps(config,indent=2))
    (out/'environment.json').write_text(json.dumps(device.metadata(),indent=2))
    values=dict(run_id=args.experiment,threads=args.threads,threshold=args.threshold,chunk_seconds=args.chunk_seconds,
        max_seconds=args.max_seconds,summary=int(args.summary),checkpoint=int(args.checkpoint),asr_model=args.model,
        model_file=model_file,embedding=args.embedding,segmentation='segmentation-model.onnx' if args.quant=='fp32' else 'segmentation-model.int8.onnx',
        min_on=args.min_on,min_off=args.min_off,window_shift_ratio=args.window_shift_ratio,
        attribution_mode=int(args.attribution=='midpoint'),cases=','.join(selected),expect_cancel=int(args.expect_cancel),
        cancel_after_frames=args.cancel_after_frames,config_hash=sha256(out/'config.json'))
    if args.cancel_stage:values['cancel_stage']=args.cancel_stage
    command=['am','instrument','-w','-r']
    for key,value in values.items():command+=['-e',key,str(value)]
    command+=[PACKAGE+'/.AudioInstrumentation']
    try:
        with (out/'stdout.log').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
            result=subprocess.run(device.adb+['shell',shlex.join(command)],env=device.env,stdout=stdout,stderr=stderr,timeout=args.timeout)
    except subprocess.TimeoutExpired:
        device.shell('am','force-stop',PACKAGE);device.logs(out)
        (out/'failure.json').write_text(json.dumps(dict(stage='instrumentation',timeout_seconds=args.timeout)))
        raise
    device.logs(out)
    if result.returncode or 'INSTRUMENTATION_RESULT: result=PASS' not in (out/'stdout.log').read_text():
        (out/'failure.json').write_text(json.dumps(dict(exit_code=result.returncode,stage='instrumentation')))
        raise RuntimeError('Android pipeline failed: '+str(out))
    def pull(name):return device.pull(args.experiment,name,out)
    metrics=json.loads(pull('metrics.json').read_text())
    for case in metrics['cases']:
        name=case['audio_id'];events=[json.loads(l) for l in pull(name+'.events.jsonl').read_text().splitlines()]
        case['cached_asr_chunks']=sum(e['stage']=='asr_cached' for e in events)
        case['asr_loads']=sum(e['stage']=='asr_load' for e in events)
        phases={}
        for event in events:
            previous=event.get('previous_stage')
            if previous:phases[previous]=phases.get(previous,0)+event['duration_ms']
        case['stage_wall_ms']=phases
        if case.get('expected_cancel'):continue
        output_path=pull(name+'.json');output=json.loads(output_path.read_text());validate(output)
        trace=json.loads(pull(name+'.json.trace.json').read_text())
        if args.summary:pull(name+'.summary.txt')
        case['audio_seconds']=max(((s['offset_frames']+s['frames'])/16000 for s in trace['asr']),default=0)
        case['full_rtf']=case['wall_ms']/1000/case['audio_seconds'] if case['audio_seconds'] else None
        if any(t['end_ms']>math.ceil(case['audio_seconds']*1000)+1 for t in output['transcript']):raise ValueError('Export exceeds source timeline')
        fixture=fixtures[name]
        if fixture.get('reference'):
            reference=ROOT/fixture['reference']
            if sha256(reference)!=fixture['reference_sha256']:raise ValueError('Changed reference')
            truth=json.loads(reference.read_text())['transcript']
            case['normalized']=counts(' '.join(t['text'] for t in truth),' '.join(t['text'] for t in output['transcript']))
            case['speaker_attributed']=cpwer(truth,output['transcript'])
        case.update(json_valid=True,transcript_sha256=sha256(output_path),
            predicted_speakers=len({r['speaker_id'] for r in output['transcript']}),expected_speakers=fixture.get('speakers'))
    metrics['normalized']=aggregate([c['normalized'] for c in metrics['cases'] if 'normalized' in c])
    metrics['scope']='Android4096MiB/x86_64 native file pipeline; timings and sampled PSS on actual AVD'
    (out/'scored-metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for source,target in [('scored-metrics.json','metrics.json'),('config.json','config.json'),('environment.json','environment.json')]:
        (report/target).write_bytes((out/source).read_bytes())
    print(json.dumps(metrics,indent=2),flush=True)


if __name__=='__main__':main()
