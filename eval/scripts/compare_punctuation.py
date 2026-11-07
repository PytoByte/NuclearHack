#!/usr/bin/env python3
"""Frozen text-v2 comparison of raw CTC, e2e CTC and CTC + word-preserving tagger."""
import argparse
import json
import time
import sys
import numpy as np
from native_sdk import ROOT,record_harness
from scoring import text_metrics,aggregate
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256

def prf(c):
    tp,fp,fn=(c[k] for k in ['true_positive','false_positive','false_negative'])
    return dict(**c,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
                f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)

def summarize(rows):
    result={k:aggregate([r[k] for r in rows]) for k in ['normalized','raw','punctuation_token_wer']}
    for k in ['normalized_cer','raw_cer']:
        errors=sum(r[k]['errors'] for r in rows);total=sum(r[k]['reference_characters'] for r in rows)
        result[k]=dict(errors=errors,reference_characters=total,cer=errors/total if total else None)
    def combine(items):return prf({k:sum(x[k] for x in items) for k in ['true_positive','false_positive','false_negative']})
    result['punctuation']={k:combine([r['punctuation'][k] for r in rows]) for k in ['end_to_end','conditional_equal_words']}
    result['punctuation']['per_mark']={p:combine([r['punctuation']['per_mark'][p] for r in rows]) for p in rows[0]['punctuation']['per_mark']}
    return result

def main():
    from punctuation import RUPunct
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True)
    p.add_argument('--baseline',required=True);p.add_argument('--e2e',required=True)
    p.add_argument('--manifest',default='eval/data/russian-conversation-pilot.jsonl');args=p.parse_args()
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    lock=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    model=next(m for m in lock['models'] if m['id']=='rupunct-small-int8')
    files=[f for f in lock['files'] if f['path'] in model['files']]
    for f in files:
        if sha256(ROOT/f['path'])!=f['sha256']:raise ValueError('Changed punctuation model')
    config=dict(vars(args),model=model,model_files=files,policy='text-v2',context_words=100,
                manifest_sha256=sha256(ROOT/args.manifest),scope='silver conversational pilot; CPU ORT1.23.2, not mobile punctuation inference')
    record_harness(out,config);(out/'config.json').write_text(json.dumps(config,indent=2))
    start=time.perf_counter();punct=RUPunct();load=time.perf_counter()-start
    rows=[];latency=0
    for fixture in map(json.loads,(ROOT/args.manifest).read_text().splitlines()):
        ident=fixture['audio_id'];reference=ROOT/fixture['reference']
        if sha256(reference)!=fixture['reference_sha256']:raise ValueError('Changed reference')
        truth=' '.join(t['text'] for t in json.loads(reference.read_text())['transcript'])
        texts={};chunks={}
        for key,eid in [('ctc',args.baseline),('e2e',args.e2e)]:
            path=ROOT/'.audio-runs'/eid/ident/'transcript.json.trace.json'
            chunks[key]=[r['backend']['text'] for r in json.loads(path.read_text())['asr']]
            texts[key]=' '.join(chunks[key]);config.setdefault('input_sha256',{})[str(path.relative_to(ROOT))]=sha256(path)
        start=time.perf_counter();texts['ctc_rupunct']=' '.join(punct(s) for s in chunks['ctc']);latency+=time.perf_counter()-start
        rows.append(dict(audio_id=ident,scores={k:text_metrics(truth,t) for k,t in texts.items()}))
        (out/(ident+'.json')).write_text(json.dumps(dict(reference=truth,hypotheses=texts),ensure_ascii=False,indent=2))
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],cases=rows,tagger_load_seconds=load,tagger_inference_seconds=latency,
                 variants={k:summarize([r['scores'][k] for r in rows]) for k in texts})
    rng=np.random.default_rng(42);diff=[]
    for _ in range(2000):
        sampled=[rows[i] for i in rng.integers(0,len(rows),len(rows))]
        def wer(k):return aggregate([r['scores'][k]['normalized'] for r in sampled])['wer']
        diff.append(wer('e2e')-wer('ctc'))
    metrics['e2e_minus_ctc_wer_paired_recording_bootstrap']=dict(seed=42,samples=2000,ci95=np.quantile(diff,[.025,.975]).tolist(),n_recordings=len(rows),limitation='only three silver sessions; speaker independence unverified')
    (out/'config.json').write_text(json.dumps(config,indent=2));(out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['metrics.json','config.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps({k:dict(wer=v['normalized']['wer'],punct_wer=v['punctuation_token_wer']['wer'],cer=v['normalized_cer']['cer'],punctuation=v['punctuation']['end_to_end']) for k,v in metrics['variants'].items()},indent=2))

if __name__=='__main__':main()
