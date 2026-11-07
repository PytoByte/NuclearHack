#!/usr/bin/env python3
"""Paired fresh-process Android profiles; OS file cache is deliberately not cleared."""
import argparse
import json
import re
import statistics
import jiwer
from scoring import normalize
from verify_refinement import canonical_turns
from native_sdk import ROOT,record_harness
import sys
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True)
    p.add_argument('--pair',nargs=2,action='append',required=True);p.add_argument('--host-baseline',required=True);p.add_argument('--host-refinement',required=True)
    args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    config=dict(vars(args),input_sha256={},scope='Android4096MiB/x86_64, fresh process per run, three paired reloads; OS cache not cleared; not ARM/cold-boot throughput')
    record_harness(out,config);(out/'config.json').write_text(json.dumps(config,indent=2));pairs=[];apk_hashes=set();manifests=set()
    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))]=sha256(path);return json.loads(path.read_text())
    for left,right in args.pair:
        row={}
        for key,eid,host in [('baseline',left,args.host_baseline),('refinement',right,args.host_refinement)]:
            c=read(ROOT/'eval/results'/eid/'config.json');m=read(ROOT/'eval/results'/eid/'metrics.json')
            apk_hashes.add(c['apk_sha256']);manifests.add(c['manifest_sha256'])
            if c['abi']!='x86_64' or not c['device_input_sha_verified']:raise ValueError('Unverified Android inputs/ABI')
            if len(m['cases'])!=1:raise ValueError('Profile one fixed recording per process')
            case=m['cases'][0];ident=case['audio_id']
            if not case.get('decoded_frames_verified'):raise ValueError('Decoded duration was not independently verified')
            actual=read(ROOT/'.audio-runs'/eid/(ident+'.json'));truth=read(ROOT/'.audio-runs'/host/ident/'transcript.json')
            delta=jiwer.process_words(normalize(' '.join(t['text'] for t in truth['transcript'])),normalize(' '.join(t['text'] for t in actual['transcript'])))
            case=dict(case,experiment_id=eid,host_transcript_equal=actual==truth,host_device_word_edits=dict(substitutions=delta.substitutions,deletions=delta.deletions,insertions=delta.insertions))
            row[key+'_trace']=read(ROOT/'.audio-runs'/eid/(ident+'.json.trace.json'))
            row[key]=case
        if row['baseline']['normalized']!=row['refinement']['normalized']:raise ValueError('Refinement altered lexical counts')
        if row['baseline_trace']['words']!=row['refinement_trace']['words']:raise ValueError('Device refinement altered ASR words/timestamps')
        if canonical_turns(row['baseline_trace']['speaker_turns'])!=canonical_turns(row['refinement_trace']['initial_speaker_turns']):raise ValueError('Initial device diarization differs')
        del row['baseline_trace'];del row['refinement_trace']
        row['device_words_and_initial_diarization_equal']=True
        row['wall_ratio']=row['refinement']['wall_ms']/row['baseline']['wall_ms'];pairs.append(row)
    if len(apk_hashes)!=1 or len(manifests)!=1:raise ValueError('Compared different APK/input versions')
    summary={}
    for key in ['baseline','refinement']:
        values=[r[key] for r in pairs]
        summary[key]=dict(median_wall_ms=statistics.median(v['wall_ms'] for v in values),median_rtf=statistics.median(v['full_rtf'] for v in values),
            max_sampled_pss_kib=max(v['sampled_peak_pss_kib'] for v in values),max_process_lifetime_rss_kib=max(v['process_lifetime_peak_rss_kib'] for v in values),
            cpwer=values[0]['speaker_attributed']['cpwer'],all_host_transcripts_equal=all(v['host_transcript_equal'] for v in values),
            median_stage_wall_ms={stage:statistics.median(v['stage_wall_ms'].get(stage,0) for v in values) for stage in set().union(*(v['stage_wall_ms'] for v in values))})
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],pairs=pairs,summary=summary,median_paired_wall_ratio=statistics.median(r['wall_ratio'] for r in pairs))
    (out/'config.json').write_text(json.dumps(config,indent=2));(out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['config.json','metrics.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
