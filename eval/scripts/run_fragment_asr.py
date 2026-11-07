#!/usr/bin/env python3
"""Quality of complete annotated turns versus short offline fragments.

This measures context loss and service time; it does not implement a causal model,
real-time capture, stable partials, overlap/dedup or diarization streaming.
"""
import argparse
import json
import time
import sys
from native_sdk import NativeSdk,ROOT,record_build
from scoring import text_metrics
from compare_punctuation import summarize
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True)
    p.add_argument('--manifest',default='eval/data/russian-conversation-pilot.jsonl');p.add_argument('--model',default='giga-v3-ctc')
    args=p.parse_args();out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    catalog=json.loads((ROOT/'config/audio-models.lock.json').read_text());model=next(m for m in catalog['models'] if m['id']==args.model)
    files=[f for f in catalog['files'] if f['path'] in model['files']]
    for f in files:
        if sha256(ROOT/f['path'])!=f['sha256']:raise ValueError('Changed model')
    config=dict(vars(args),selection='first four publisher turns per session with 8<=duration<=25s and no annotated overlap',
        chunk_seconds=[None,2,5,10],threads=4,model_files=files,sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),
        manifest_sha256=sha256(ROOT/args.manifest),scope='host offline fragmented decode; silver references; no ARM or causal streaming claim')
    record_build(out,config);(out/'config.json').write_text(json.dumps(config,indent=2))
    sdk=NativeSdk();handle=sdk.create(model['family'],model['files'],4)
    results=[]
    try:
        for fixture in map(json.loads,(ROOT/args.manifest).read_text().splitlines()):
            audio=ROOT/fixture['audio'];ref=ROOT/fixture['reference']
            if sha256(audio)!=fixture['audio_sha256'] or sha256(ref)!=fixture['reference_sha256']:raise ValueError('Changed corpus')
            turns=json.loads(ref.read_text())['transcript'];pcm=sdk.decode(audio)
            selected=[(i,t) for i,t in enumerate(turns) if 8000<=t['end_ms']-t['start_ms']<=25000 and not any(
                j!=i and min(t['end_ms'],v['end_ms'])>max(t['start_ms'],v['start_ms']) for j,v in enumerate(turns))][:4]
            for index,turn in selected:
                samples=pcm[turn['start_ms']*16:turn['end_ms']*16]
                for seconds in [None,2,5,10]:
                    size=round(seconds*16000) if seconds else len(samples);hyp=[];latencies=[]
                    for offset in range(0,len(samples),size):
                        start=time.perf_counter();hyp.append(sdk.transcribe(handle,samples[offset:offset+size])['text']);latencies.append(time.perf_counter()-start)
                    text=' '.join(hyp);results.append(dict(audio_id=fixture['audio_id'],turn_index=index,chunk_seconds=seconds,
                        audio_seconds=len(samples)/16000,inference_seconds=sum(latencies),max_fragment_service_seconds=max(latencies),
                        hypothesis=text,scores=text_metrics(turn['text'],text)))
    finally:sdk.lib.nh_asr_destroy(handle)
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],segments=len(results)//4,
        variants={str(seconds):dict(**summarize([r['scores'] for r in results if r['chunk_seconds']==seconds]),
            inference_rtf=sum(r['inference_seconds'] for r in results if r['chunk_seconds']==seconds)/sum(r['audio_seconds'] for r in results if r['chunk_seconds']==seconds)) for seconds in [None,2,5,10]})
    (out/'per_turn.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results))
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['metrics.json','config.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps({k:dict(wer=v['normalized']['wer'],rtf=v['inference_rtf']) for k,v in metrics['variants'].items()}))

if __name__=='__main__':main()
