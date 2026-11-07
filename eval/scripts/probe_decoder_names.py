#!/usr/bin/env python3
"""Public C ABI regression: PCM WAV with embedded MP3 sync bytes must ignore suffix hints."""
import argparse
import json
import re
import wave
import numpy as np
from native_sdk import NativeSdk,ROOT,record_build
import sys
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True);p.add_argument('--expect-mismatch',action='store_true');args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    config=dict(vars(args),sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),scope='decoder filename-hint regression; no ASR inference')
    record_build(out,config);sdk=NativeSdk();synthetic=out/'embedded-sync.wav'
    payload=((bytes.fromhex('fffb9064')+bytes(413))*70)[:32000].ljust(32000,b'\0')
    with wave.open(str(synthetic),'wb') as f:f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(payload)
    movie=json.loads((ROOT/'eval/data/russian-conversation-movie-session.jsonl').read_text())
    source=ROOT/movie['audio']
    if sha256(source)!=movie['audio_sha256']:raise ValueError('Changed movie source')
    cases=[]
    for name,wav in [('synthetic',synthetic),('movie',source)]:
        renamed=out/(name+'.mp3');renamed.symlink_to(wav.resolve())
        a=sdk.decode(wav);b=sdk.decode(renamed);equal=np.array_equal(a,b)
        if equal==args.expect_mismatch:raise AssertionError('Unexpected filename-hint behavior: '+name)
        cases.append(dict(case=name,source_sha256=sha256(wav),wav_frames=len(a),same_bytes_mp3_frames=len(b),pcm_equal=equal))
    metrics=dict(experiment_id=args.experiment,cases=cases,expected_mismatch=args.expect_mismatch,scope=config['scope'])
    (out/'config.json').write_text(json.dumps(config,indent=2));(out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['config.json','metrics.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':main()
