#!/usr/bin/env python3
"""Final six-record punctuation A/B on frozen native posterior-file outputs.

Compare original ASR chunks with actual speaker utterances as text context.
Lexical content, speaker IDs and times must stay unchanged after restoration.
Taggers are research Python/ORT here, not a claim of native integration.
"""
import argparse
import json
import re
import resource
import sys
import time
from native_sdk import ROOT, record_harness
from scoring import normalize, text_metrics
from punctuation import RUPunct, HorizonPunct
from compare_punctuation import summarize
from run_file_pipeline import cpwer
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256

SOURCES=[('eval/data/russian-conversation-pilot.jsonl','exp_0205'),
 ('eval/data/russian-conversation-heldout-session.jsonl','exp_0207'),
 ('eval/data/russian-conversation-movie-session.jsonl','exp_0206'),
 ('eval/data/russian-conversation-astrology-session.jsonl','exp_0208')]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',required=True);args=parser.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):parser.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    lock=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    selected=[m for m in lock['models'] if m['id'] in ['rupunct-small-int8','horizon-punct-small']]
    wanted={p for m in selected for p in m['files']};files=[f for f in lock['files'] if f['path'] in wanted]
    for f in files:
        if sha256(ROOT/f['path'])!=f['sha256']:raise ValueError('Changed pinned model')
    config=dict(vars(args),model_files=files,model_lock_sha256=sha256(ROOT/'config/audio-models.lock.json'),
      input_sha256={},threads=4,context_words=100,scope='six known RU silver records; Python ORT punctuation block on actual fixed native words/turns; no target integration or ARM performance claim',
      variants=['raw','rupunct_chunks','rupunct_turns','horizon_chunks','horizon_turns'])
    record_harness(out,config);(out/'config.json').write_text(json.dumps(config,indent=2))
    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))]=sha256(path)
        return json.loads(path.read_text())
    cases=[];load={};times={name:0. for name in config['variants']}
    # One tagger at a time; avoid overlapping model lifetimes.
    for model_name,cls in [('rupunct',RUPunct),('horizon',HorizonPunct)]:
        began=time.perf_counter();tagger=cls(threads=4);load[model_name]=time.perf_counter()-began
        for manifest,baseline in SOURCES:
            config['input_sha256'][manifest]=sha256(ROOT/manifest)
            for entry in map(json.loads,(ROOT/manifest).read_text().splitlines()):
                ident=entry['audio_id'];folder=ROOT/'.audio-runs'/baseline/ident
                truth=read(ROOT/entry['reference'])['transcript']
                if config['input_sha256'][entry['reference']]!=entry['reference_sha256']:raise ValueError('Changed reference')
                actual=read(folder/'transcript.json')['transcript'];trace=read(folder/'transcript.json.trace.json')
                expected=' '.join(t['text'] for t in actual);target=' '.join(t['text'] for t in truth)
                previous=next((c for c in cases if c['audio_id']==ident),None)
                if previous is None:
                    previous=dict(audio_id=ident,audio_seconds=entry['audio_seconds'],baseline=baseline,variants={'raw':text_metrics(target,expected)},timings={},lexical_text_identical=True)
                    cases.append(previous)
                hypotheses={}
                for context in ['chunks','turns']:
                    source=[r['backend']['text'] for r in trace['asr']] if context=='chunks' else [r['text'] for r in actual]
                    if normalize(' '.join(source))!=normalize(expected):raise ValueError('Different fixed ASR text')
                    began=time.perf_counter();decorated=[tagger(text) for text in source];elapsed=time.perf_counter()-began
                    text=' '.join(decorated);name=model_name+'_'+context
                    if normalize(text)!=normalize(expected):raise ValueError('Punctuation altered words')
                    if context=='turns':
                        rows=[dict(row,text=decorated[i]) for i,row in enumerate(actual)]
                        if cpwer(truth,rows)!=cpwer(truth,actual):raise ValueError('Lexical cpWER changed')
                        hypotheses[name]=rows
                    else:hypotheses[name]=text
                    previous['variants'][name]=text_metrics(target,text);previous['timings'][name]=elapsed;times[name]+=elapsed
                (out/(ident+'.'+model_name+'.json')).write_text(json.dumps(hypotheses,ensure_ascii=False,indent=2))
                print(json.dumps(dict(model=model_name,audio_id=ident,timings=previous['timings'])),flush=True)
        del tagger
    variants={name:summarize([c['variants'][name] for c in cases]) for name in config['variants']}
    duration=sum(c['audio_seconds'] for c in cases)
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],cases=cases,variants=variants,
      tagger_load_seconds=load,tagger_inference_seconds=times,inference_rtf={k:v/duration for k,v in times.items()},
      process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      limitation='Process lifetime peak covers sequential Python/ORT taggers and scoring; not SDK/Android RAM. Known silver punctuation style, no new independent gold.')
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name,value in [('config.json',config),('metrics.json',metrics)]:
        (out/name).write_text(json.dumps(value,indent=2));(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps({k:dict(wer=v['normalized']['wer'],punct_wer=v['punctuation_token_wer']['wer'],f1=v['punctuation']['end_to_end']['f1']) for k,v in variants.items()}),flush=True)


if __name__=='__main__':main()
