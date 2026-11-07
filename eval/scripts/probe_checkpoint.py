#!/usr/bin/env python3
"""Real-model cancel/resume/cache invalidation checks through the public file C ABI."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from native_sdk import ROOT,NativeSdk,record_build
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256
from audio_tools import transcript as validate

class Pipeline(C.Structure):
    _fields_=[('struct_size',C.c_uint32)]+[(n,C.c_char_p) for n in
        ('asr_model','tokens','segmentation','embedding','scratch_directory','output_json','trace_json')]+[
        ('threads',C.c_uint32),('chunk_seconds',C.c_uint32),('max_audio_seconds',C.c_uint32),('cluster_threshold',C.c_float)]
class Options(C.Structure):
    _fields_=[('struct_size',C.c_uint32),('min_duration_on',C.c_float),('min_duration_off',C.c_float),
        ('attribution_mode',C.c_uint32),('checkpoint_directory',C.c_char_p),('window_shift_ratio',C.c_float)]
PROGRESS=C.CFUNCTYPE(C.c_int32,C.c_char_p,C.c_uint64,C.c_uint64,C.c_void_p)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True);args=p.parse_args()
    if not args.experiment.startswith('exp_') or not args.experiment[4:].isdigit():p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    log=(out/'stderr.log').open('w');os.dup2(log.fileno(),2)
    cache=out/'cache';cache.mkdir()
    fixture=ROOT/'eval/data/audio/dialogs-clean_2.mp3'
    config=dict(experiment_id=args.experiment,scope='Linux native C ABI functional checkpoint test; not Android timing',
        input_sha256=sha256(fixture),sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),threads=4,chunk_seconds=20)
    record_build(out,config);(out/'config.json').write_text(json.dumps(config,indent=2))
    config_hash=sha256(out/'config.json')
    sdk=NativeSdk();lib=sdk.lib
    lib.nh_transcribe_file_with_options.argtypes=[C.c_char_p,C.POINTER(Pipeline),C.POINTER(Options),PROGRESS,C.c_void_p]
    cases=[]
    def run(name,*,chunk=20,cache_dir=cache,audio=fixture,cancel=None,expected=0):
        directory=out/name;directory.mkdir();output=directory/'transcript.json';trace=directory/'trace.json'
        paths=[ROOT/'models/giga-v3-ctc/model.int8.onnx',ROOT/'models/giga-v3-ctc/tokens.txt',
            ROOT/'models/diarization/segmentation-model.onnx',ROOT/'models/diarization/embedding.onnx',directory,output,trace]
        base=Pipeline(C.sizeof(Pipeline),*[os.fsencode(q) for q in paths],4,chunk,600,.8)
        options=Options(C.sizeof(Options),.3,.5,0,os.fsencode(cache_dir),.1)
        stages=[];began=time.perf_counter();previous=began
        @PROGRESS
        def progress(stage,done,total,user):
            nonlocal previous
            stage=stage.decode();now=time.perf_counter();stages.append(stage)
            stop=bool(cancel and cancel(stage,done))
            rss=int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))
            event=dict(run_id=args.experiment,audio_id='dialogs-clean_2',case=name,stage=stage,
                start_ms=round((previous-began)*1000),duration_ms=round((now-previous)*1000),memory_mb=rss/1024,
                memory_kind='current_rss',status='cancel_requested' if stop else 'processing',
                model='giga-v3-ctc' if stage.startswith('asr') else 'pyannote-eres2net-fp32',config_hash=config_hash)
            previous=now
            with (directory/'events.jsonl').open('a') as target:target.write(json.dumps(event)+'\n')
            return int(stop)
        status=lib.nh_transcribe_file_with_options(os.fsencode(audio),C.byref(base),C.byref(options),progress,None)
        result=dict(case=name,status=status,expected_status=expected,wall_seconds=time.perf_counter()-began,
            input_sha256=sha256(audio),chunk_seconds=chunk,
            cached_chunks=stages.count('asr_cached'),asr_loads=stages.count('asr_load'),
            output_exists=output.exists(),error=lib.nh_last_error().decode() if status else '')
        cases.append(result);(directory/'result.json').write_text(json.dumps(result,indent=2))
        if status!=expected:raise AssertionError(result)
        if status==0:validate(json.loads(output.read_text()))
        else:
            if output.exists():raise AssertionError('Failed/cancelled job committed final export')
        return output,result
    run('cancel_after_first_chunk',cancel=lambda stage,done:stage=='asr' and done>0,expected=4)
    checkpoint=next(cache.glob('*.json'));partial=json.loads(checkpoint.read_text())
    if len(partial['asr'])!=1:raise AssertionError('First completed chunk was not persisted')
    samples=sdk.decode(fixture)
    if partial['identity']['decoded_pcm_sha256']!=hashlib.sha256(samples.tobytes()).hexdigest():raise AssertionError('Native PCM SHA differs')
    if partial['identity']['asr_sha256']!=sha256(ROOT/'models/giga-v3-ctc/model.int8.onnx'):raise AssertionError('Native model SHA differs')
    resumed,r=run('resume');cached,c=run('fully_cached')
    if r['cached_chunks']!=1 or c['cached_chunks']!=2 or c['asr_loads']!=0 or sha256(resumed)!=sha256(cached):
        raise AssertionError('Replay loaded ASR or changed transcript')
    fresh_cache=out/'fresh-cache';fresh_cache.mkdir()
    fresh,_=run('fresh_control',cache_dir=fresh_cache)
    if sha256(fresh)!=sha256(resumed):raise AssertionError('Resume changed the fresh-control transcript')
    _,changed=run('chunk_config_changed',chunk=10,cancel=lambda stage,done:stage=='asr_load',expected=4)
    if changed['cached_chunks']:raise AssertionError('Reused cache after config change')
    scaled=out/'changed-input.wav'
    subprocess.run([str(ROOT/'.tools/bin/ffmpeg'),'-v','error','-i',str(fixture),'-af','volume=0.5','-ar','16000',str(scaled)],check=True)
    _,changed=run('input_changed',audio=scaled,cancel=lambda stage,done:stage=='asr_load',expected=4)
    if changed['cached_chunks']:raise AssertionError('Reused cache after input change')
    bad=out/'bad-cache';bad.mkdir();corrupt=json.loads(checkpoint.read_text());corrupt['identity']['decoded_pcm_sha256']='0'*64
    (bad/checkpoint.name).write_text(json.dumps(corrupt))
    before=sha256(checkpoint);run('corrupt_cache_rejected',cache_dir=bad,expected=3)
    if sha256(checkpoint)!=before:raise AssertionError('Good cache changed during invalid-cache test')
    metrics=dict(experiment_id=args.experiment,cases=cases,passed=True,
        main_transcript_byte_identical=True,fully_cached_asr_loads=0,native_sha256_matches_python=True,scope=config['scope'])
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    (out/'environment.json').write_text(json.dumps(dict(host=platform.platform(),
        git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ('config.json','metrics.json','environment.json'):(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics,indent=2),flush=True)


if __name__=='__main__':main()
