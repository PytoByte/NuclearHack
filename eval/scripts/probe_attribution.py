#!/usr/bin/env python3
"""Diagnostic reference-turn oracle and timestamp sensitivity; never production input."""
import argparse
import json
import re
import sys
from native_sdk import ROOT,record_harness
from run_file_pipeline import cpwer
from scoring import normalize,speaker_coverage
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


def attribute(words,turns,shift_ms=0):
    result=[]
    for original in words:
        word=dict(original);word['start_ms']+=shift_ms;word['end_ms']+=shift_ms
        best=0;speaker='speaker_unknown'
        for turn in turns:
            overlap=max(0,min(word['end_ms'],turn['end_ms'])-max(word['start_ms'],turn['start_ms']))
            if overlap>best:best=overlap;speaker=turn['speaker_id']
        if result and result[-1]['speaker_id']==speaker and word['start_ms']-result[-1]['end_ms']<=1200:
            result[-1]['end_ms']=max(result[-1]['end_ms'],word['end_ms']);result[-1]['text']+=' '+word['text']
        else:result.append(dict(speaker_id=speaker,start_ms=word['start_ms'],end_ms=word['end_ms'],text=word['text']))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True)
    p.add_argument('--baseline',default='exp_0069');p.add_argument('--manifest',default='eval/data/russian-conversation-pilot.jsonl');args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    config=dict(vars(args),scope='reference speaker-turn oracle; silver timing sensitivity, not word timestamp accuracy or deployable quality',
                shift_ms=[-200,-100,0,100,200],manifest_sha256=sha256(ROOT/args.manifest),input_sha256={})
    record_harness(out,config);cases=[]
    for f in map(json.loads,(ROOT/args.manifest).read_text().splitlines()):
        directory=ROOT/'.audio-runs'/args.baseline/f['audio_id'];trace_path=directory/'transcript.json.trace.json';actual_path=directory/'transcript.json';ref=ROOT/f['reference']
        if sha256(ref)!=f['reference_sha256']:raise ValueError('Changed reference')
        for path in [trace_path,actual_path]:config['input_sha256'][str(path.relative_to(ROOT))]=sha256(path)
        trace=json.loads(trace_path.read_text());actual=json.loads(actual_path.read_text())['transcript'];truth=json.loads(ref.read_text())['transcript']
        ids={};turns=[]
        for t in trace['speaker_turns']:
            if t['speaker'] not in ids:ids[t['speaker']]='speaker_'+str(len(ids)+1)
            turns.append(dict(start_ms=t['start_ms'],end_ms=t['end_ms'],speaker_id=ids[t['speaker']]))
        reproduced=attribute(trace['words'],turns)
        if reproduced!=actual:raise ValueError('Diagnostic attribution differs from native production merge')
        variants={'baseline_reproduced':reproduced}
        variants.update({'oracle_shift_'+str(shift):attribute(trace['words'],truth,shift) for shift in config['shift_ms']})
        original_words=normalize(' '.join(t['text'] for t in actual))
        for rows in variants.values():
            if normalize(' '.join(t['text'] for t in rows))!=original_words:raise ValueError('Diagnostic altered lexical sequence')
        cases.append(dict(audio_id=f['audio_id'],native_merge_reproduced=True,variants={k:dict(speaker_attributed=cpwer(truth,v),**speaker_coverage(v)) for k,v in variants.items()}))
    aggregate={}
    for name in cases[0]['variants']:
        errors=sum(c['variants'][name]['speaker_attributed']['errors'] for c in cases)
        words=sum(c['variants'][name]['speaker_attributed']['reference_words'] for c in cases)
        aggregate[name]=dict(errors=errors,reference_words=words,cpwer=errors/words)
    result=dict(experiment_id=args.experiment,scope=config['scope'],cases=cases,variants=aggregate)
    (out/'config.json').write_text(json.dumps(config,indent=2));(out/'metrics.json').write_text(json.dumps(result,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['config.json','metrics.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(aggregate,indent=2))

if __name__=='__main__':main()
