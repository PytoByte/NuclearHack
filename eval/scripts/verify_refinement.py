#!/usr/bin/env python3
"""Verify native opt-in refinement equals the frozen research prototype."""
import argparse
import json
import re
import sys
from native_sdk import ROOT,record_harness
from probe_attribution import attribute
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256
from audio_tools import transcript as validate


def canonical_turns(turns):
    ids={};result=[]
    for t in turns:
        if t['speaker'] not in ids:ids[t['speaker']]=len(ids)+1
        result.append(dict(t,speaker=ids[t['speaker']]))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True)
    p.add_argument('--case-set',nargs=4,action='append',required=True,metavar=('NATIVE','BASELINE','PROTOTYPE','MANIFEST'))
    args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    config=dict(vars(args),threshold=.4,input_sha256={});record_harness(out,config);cases=[]
    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))]=sha256(path);return json.loads(path.read_text())
    for native,baseline,prototype,manifest in args.case_set:
        config['input_sha256'][manifest]=sha256(ROOT/manifest)
        prototype_rows={r['audio_id']:r for r in read(ROOT/'eval/results'/prototype/'metrics.json')['cases']}
        for f in map(json.loads,(ROOT/manifest).read_text().splitlines()):
            ident=f['audio_id'];base_trace=read(ROOT/'.audio-runs'/baseline/ident/'transcript.json.trace.json')
            actual_trace=read(ROOT/'.audio-runs'/native/ident/'transcript.json.trace.json')
            actual=read(ROOT/'.audio-runs'/native/ident/'transcript.json');validate(actual)
            if actual_trace['words']!=base_trace['words']:raise ValueError('Native refinement altered ASR word text/timestamps: '+ident)
            if canonical_turns(actual_trace['initial_speaker_turns'])!=canonical_turns(base_trace['speaker_turns']):raise ValueError('Initial diarization changed: '+ident)
            mapping=prototype_rows[ident]['variants']['0.4']['mapping'];original_ids={};canonical={};expected_turns=[]
            for t in base_trace['speaker_turns']:
                if t['speaker'] not in original_ids:original_ids[t['speaker']]='speaker_'+str(len(original_ids)+1)
                group=mapping[original_ids[t['speaker']]]
                if group not in canonical:canonical[group]='speaker_'+str(len(canonical)+1)
                expected_turns.append(dict(start_ms=t['start_ms'],end_ms=t['end_ms'],speaker_id=canonical[group]))
            expected=attribute(base_trace['words'],expected_turns)
            if actual['transcript']!=expected:raise ValueError('Native/prototype speaker partition or merge differs: '+ident)
            cases.append(dict(audio_id=ident,native=native,prototype=prototype,words_unchanged=True,initial_diarization_unchanged=True,
                full_transcript_equal_after_canonical_ids=True,refinement=actual_trace['speaker_refinement']))
    metrics=dict(experiment_id=args.experiment,cases=cases,scope='Native/prototype exact transcript equality after deterministic speaker renumbering; all words/timestamps preserved')
    (out/'config.json').write_text(json.dumps(config,indent=2));(out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['config.json','metrics.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':main()
