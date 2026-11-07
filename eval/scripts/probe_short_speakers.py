#!/usr/bin/env python3
"""Diagnostic only: separate clustering-count effects from timestamp attribution.

Known source occupancy and oracle K are never fed into the production pipeline.
The acted fixture's occupancy spans are not true speech/word RTTM ground truth.
"""
import argparse
import ctypes as C
import json
import os
import re
import sys
import numpy as np
from native_sdk import ROOT,NativeSdk,DiarConfig,TURN,record_build
from probe_attribution import attribute
from run_file_pipeline import cpwer
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True);args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    log=(out/'stderr.log').open('w');os.dup2(log.fileno(),2)
    fixture=next(r for r in map(json.loads,(ROOT/'eval/data/dialogs-smoke.jsonl').read_text().splitlines()) if r['audio_id']=='dialogs-pauses_short_3')
    audio=ROOT/fixture['audio'];ref=ROOT/fixture['reference']
    if sha256(audio)!=fixture['audio_sha256'] or sha256(ref)!=fixture['reference_sha256']:raise ValueError('Changed synthetic reference')
    source=ROOT/'.audio-runs/exp_0125/dialogs-pauses_short_3/transcript.json.trace.json';trace=json.loads(source.read_text());truth=json.loads(ref.read_text())['transcript']
    config=dict(vars(args),sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),input_sha256=sha256(audio),reference_sha256=sha256(ref),trace_sha256=sha256(source),
        scope='acted short-turn diagnostic, oracle count/source occupancy only; not deployable or natural DER/word timing proof')
    record_build(out,config);sdk=NativeSdk();pcm=sdk.decode(audio);lib=sdk.lib
    lib.nh_diarizer_create_with_window.argtypes=[C.POINTER(DiarConfig),C.c_float,C.POINTER(C.c_void_p)]
    lib.nh_diarizer_process.argtypes=[C.c_void_p,C.POINTER(C.c_float),C.c_uint32,TURN,C.c_void_p];lib.nh_diarizer_destroy.argtypes=[C.c_void_p]
    results=[]
    for oracle in [-1,3]:
        handle=C.c_void_p();turns=[]
        cfg=DiarConfig(C.sizeof(DiarConfig),os.fsencode(ROOT/'models/diarization/segmentation-model.onnx'),os.fsencode(ROOT/'models/diarization/embedding.onnx'),4,.8,.3,.5,oracle)
        sdk.check(lib.nh_diarizer_create_with_window(C.byref(cfg),.1,C.byref(handle)))
        @TURN
        def collect(speaker,start,end,user):
            turns.append(dict(speaker_id=str(speaker),start_ms=round(start*1000),end_ms=round(end*1000)));return 0
        try:sdk.check(lib.nh_diarizer_process(handle,pcm.ctypes.data_as(C.POINTER(C.c_float)),len(pcm),collect,None))
        finally:lib.nh_diarizer_destroy(handle)
        predicted=attribute(trace['words'],turns)
        results.append(dict(mode='auto' if oracle==-1 else 'oracle3',returned_speakers=len({t['speaker_id'] for t in turns}),speaker_attributed=cpwer(truth,predicted)))
        (out/('turns-'+str(oracle)+'.json')).write_text(json.dumps(turns,indent=2))
    results.append(dict(mode='source_occupancy_oracle',speaker_attributed=cpwer(truth,attribute(trace['words'],truth))))
    metrics=dict(experiment_id=args.experiment,cases=results,scope=config['scope'])
    (out/'config.json').write_text(json.dumps(config,indent=2));(out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['config.json','metrics.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':main()
