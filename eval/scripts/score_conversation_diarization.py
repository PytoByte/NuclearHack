#!/usr/bin/env python3
"""Post-hoc DER/JER from frozen pipeline traces against publisher silver turns."""
import argparse
import json
from native_sdk import ROOT,record_harness
from pyannote.core import Annotation, Segment, Timeline
from pyannote.metrics.diarization import DiarizationErrorRate,JaccardErrorRate
import sys
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True);p.add_argument('--runs',nargs='+',required=True)
    p.add_argument('--manifest',default='eval/data/russian-conversation-pilot.jsonl');args=p.parse_args()
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    config=dict(vars(args),collar_seconds=.25,skip_overlap=False,manifest_sha256=sha256(ROOT/args.manifest),input_sha256={})
    record_harness(out,config);metrics={}
    fixtures=list(map(json.loads,(ROOT/args.manifest).read_text().splitlines()))
    for run in args.runs:
        der=DiarizationErrorRate(collar=.25,skip_overlap=False);jer=JaccardErrorRate(collar=.25,skip_overlap=False);cases=[]
        for f in fixtures:
            path=ROOT/'.audio-runs'/run/f['audio_id']/'transcript.json.trace.json';ref=ROOT/f['reference']
            if sha256(ref)!=f['reference_sha256']:raise ValueError('Changed reference')
            config['input_sha256'][str(path.relative_to(ROOT))]=sha256(path)
            truth=json.loads(ref.read_text())['transcript'];turns=json.loads(path.read_text())['speaker_turns']
            a,b=Annotation(uri=f['audio_id']),Annotation(uri=f['audio_id'])
            for i,t in enumerate(truth):a[Segment(t['start_ms']/1000,t['end_ms']/1000),i]=t['speaker_id']
            for i,t in enumerate(turns):b[Segment(t['start_ms']/1000,t['end_ms']/1000),i]=str(t['speaker'])
            uem=Timeline([Segment(0,f['audio_seconds'])])
            score=der(a,b,uem=uem,detailed=True);j=jer(a,b,uem=uem)
            cases.append(dict(audio_id=f['audio_id'],der_details={k:float(v) for k,v in score.items()},jer=float(j),
                              reference_speakers=len(a.labels()),predicted_speakers=len(b.labels())))
        metrics[run]=dict(der=abs(der),jer=abs(jer),cases=cases)
    result=dict(experiment_id=args.experiment,scope='Russian conversational silver pilot: publisher turns, not independently audited gold; diagnostic DER/JER',runs=metrics)
    (out/'config.json').write_text(json.dumps(config,indent=2));(out/'metrics.json').write_text(json.dumps(result,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['config.json','metrics.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps({k:dict(der=v['der'],jer=v['jer']) for k,v in metrics.items()}))

if __name__=='__main__':main()
