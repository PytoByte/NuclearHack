#!/usr/bin/env python3
"""Compare actual host f32 mono PCM with the Android checkpoint's source hash."""
import argparse
import hashlib
import json
import re
import subprocess
from native_sdk import ROOT,NativeSdk,record_build
from android_device import AndroidDevice,PACKAGE
import sys
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True);args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    fixture=json.loads((ROOT/'eval/data/russian-conversation-movie-session.jsonl').read_text());audio=ROOT/fixture['audio']
    if sha256(audio)!=fixture['audio_sha256']:raise ValueError('Changed source')
    device=AndroidDevice();relative='files/job-cache/'+fixture['audio_id']
    names=[n for n in device.shell('run-as',PACKAGE,'ls',relative).splitlines() if re.fullmatch(r'asr-[0-9a-f]{64}\.json',n)]
    if len(names)!=1:raise ValueError('Expected one unambiguous Android checkpoint for this frozen source')
    data=subprocess.check_output(device.adb+['exec-out','run-as',PACKAGE,'cat',relative+'/'+names[0]],env=device.env)
    (out/'android-checkpoint.json').write_bytes(data);cache=json.loads(data)
    samples=NativeSdk().decode(audio);host=hashlib.sha256(samples.astype('<f4',copy=False).tobytes()).hexdigest();target=cache['identity']['decoded_pcm_sha256']
    if host!=target:raise AssertionError('Host/Android decoded PCM differs')
    config=dict(vars(args),sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),input_sha256=fixture['audio_sha256'],
        apk_sha256=device.apk_sha256,abi=device.abi,android_checkpoint_sha256=hashlib.sha256(data).hexdigest())
    record_build(out,config)
    metrics=dict(experiment_id=args.experiment,decoded_frames=len(samples),decoded_pcm_sha256=host,host_android_pcm_identical=True,
        cached_chunks=len(cache['asr']),scope='host/Android x86_64 exact input signal identity; ASR differences occur after decoding; exact feature/inference cause is not isolated')
    (out/'config.json').write_text(json.dumps(config,indent=2));(out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['config.json','metrics.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':main()
