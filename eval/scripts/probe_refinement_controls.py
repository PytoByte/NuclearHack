#!/usr/bin/env python3
"""Real public-C-ABI refinement cancellation, explicit cap and reentry checks."""
import argparse
import ctypes as C
import json
import os
import re
import sys
from native_sdk import ROOT,NativeSdk,record_build
from probe_checkpoint import Pipeline,Options,PROGRESS
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256

class Refinement(C.Structure):
    _fields_=[('struct_size',C.c_uint32),('cluster_threshold',C.c_float),('max_clusters',C.c_uint32)]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True);args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    diagnostics=(out/'stderr.log').open('w');os.dup2(diagnostics.fileno(),2)
    audio=ROOT/'eval/data/audio/dialogs-clean_2.mp3'
    lock=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    selected={'models/giga-v3-ctc/model.int8.onnx','models/giga-v3-ctc/tokens.txt','models/diarization/segmentation-model.onnx','models/diarization/embedding.onnx'}
    files=[f for f in lock['files'] if f['path'] in selected]
    for f in files:
        if sha256(ROOT/f['path'])!=f['sha256']:raise ValueError('Changed model')
    config=dict(vars(args),sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),model_files=files,
        input_sha256=sha256(audio),scope='host native real-model control behavior; no quality/ARM timing claim')
    record_build(out,config);(out/'config.json').write_text(json.dumps(config,indent=2))
    sdk=NativeSdk();lib=sdk.lib
    lib.nh_transcribe_file_with_options.argtypes=[C.c_char_p,C.POINTER(Pipeline),C.POINTER(Options),PROGRESS,C.c_void_p]
    lib.nh_transcribe_file_with_refinement.argtypes=[C.c_char_p,C.POINTER(Pipeline),C.POINTER(Options),C.POINTER(Refinement),PROGRESS,C.c_void_p]
    cache=out/'cache';cache.mkdir();results=[]
    for name,expected,cap in [('budget_rejected',1,1),('cancel_between_embeddings',4,128),('reentrant_busy',4,128)]:
        directory=out/name;directory.mkdir();output=directory/'transcript.json';trace=directory/'trace.json'
        paths=[ROOT/'models/giga-v3-ctc/model.int8.onnx',ROOT/'models/giga-v3-ctc/tokens.txt',ROOT/'models/diarization/segmentation-model.onnx',ROOT/'models/diarization/embedding.onnx',directory,output,trace]
        base=Pipeline(C.sizeof(Pipeline),*[os.fsencode(q) for q in paths],4,20,600,.8)
        options=Options(C.sizeof(Options),.3,.5,0,os.fsencode(cache),.1)
        refinement=Refinement(C.sizeof(Refinement),.4,cap);stages=[];nested=[]
        @PROGRESS
        def progress(stage,done,total,user):
            stage=stage.decode();stages.append(dict(stage=stage,completed_frames=done,total_frames=total))
            if name=='cancel_between_embeddings' and stage=='speaker_refine' and done>0:return 1
            if name=='reentrant_busy' and stage=='speaker_refine_load':
                nested.append(lib.nh_transcribe_file_with_options(os.fsencode(audio),C.byref(base),C.byref(options),progress,None));return 1
            return 0
        status=lib.nh_transcribe_file_with_refinement(os.fsencode(audio),C.byref(base),C.byref(options),C.byref(refinement),progress,None)
        error=lib.nh_last_error().decode()
        if status!=expected:raise AssertionError(f'{name}: expected {expected}, got {status}: {error}')
        if output.exists() or trace.exists():raise AssertionError('Incomplete refinement exported a final result')
        if name=='budget_rejected' and ('cluster budget' not in error or any(s['stage']=='speaker_refine_load' for s in stages)):raise AssertionError('Cap did not fail before model load')
        if name=='cancel_between_embeddings' and not any(s['stage']=='speaker_refine' and s['completed_frames']>0 for s in stages):raise AssertionError('Cancellation did not reach completed embedding')
        if name=='reentrant_busy' and nested!=[5]:raise AssertionError('Nested operation did not return NH_BUSY')
        (directory/'events.json').write_text(json.dumps(stages,indent=2))
        results.append(dict(case=name,max_clusters=cap,status=status,error=error,final_export_absent=True,nested_status=nested,
            asr_loads=sum(s['stage']=='asr_load' for s in stages),cached_asr_chunks=sum(s['stage']=='asr_cached' for s in stages)))
    metrics=dict(experiment_id=args.experiment,cases=results,passed=True,scope=config['scope'])
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['config.json','metrics.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':main()
