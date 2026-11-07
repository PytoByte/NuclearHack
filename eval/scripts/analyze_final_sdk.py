#!/usr/bin/env python3
"""Seal measured final SDK quality, refactor parity, target and control results."""
import argparse
import json
import re
import statistics
import sys
import numpy as np
from native_sdk import ROOT, record_harness
from compare_punctuation import summarize
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


SOURCES=[('eval/data/russian-conversation-pilot.jsonl','exp_0230','exp_0219','exp_0205'),
 ('eval/data/russian-conversation-heldout-session.jsonl','exp_0231','exp_0220','exp_0207'),
 ('eval/data/russian-conversation-movie-session.jsonl','exp_0232','exp_0221','exp_0206'),
 ('eval/data/russian-conversation-astrology-session.jsonl','exp_0233','exp_0222','exp_0208')]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True);args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    config=dict(vars(args),scope='selected final native SDK audit; known RU silver quality, exact refactor parity, x86 AVD, controls and explicitly synthetic600s capacity',input_sha256={})
    record_harness(out,config)
    config['preset']=json.loads((ROOT/'config/audio-sdk-preset.json').read_text())
    def read(path):
        config['input_sha256'][str(path.relative_to(ROOT))]=sha256(path)
        return json.loads(path.read_text())
    def report(eid):return read(ROOT/'eval/results'/eid/'metrics.json')
    cases=[];old_cases=[];quality_rows=[]
    canonical_build=read(ROOT/'.build/audio/build-provenance.json')
    for manifest,new,previous,raw in SOURCES:
        entries=list(map(json.loads,(ROOT/manifest).read_text().splitlines()))
        config['input_sha256'][manifest]=sha256(ROOT/manifest)
        metrics=report(new);before=report(previous)
        old={c['audio_id']:c for c in report(raw)['cases']}
        if len(entries)!=len(metrics['cases']):raise ValueError('Different case count')
        if metrics['text_metrics']!=before['text_metrics'] or metrics['cpwer']!=before['cpwer']:raise ValueError('Refactor changed quality')
        for entry,c in zip(entries,metrics['cases']):
            ident=entry['audio_id']
            if ident!=c['audio_id']:raise ValueError('Different source set')
            current=ROOT/'.audio-runs'/new/ident;reference=ROOT/'.audio-runs'/previous/ident
            actual=read(current/'transcript.json');expected=read(reference/'transcript.json')
            trace=read(current/'transcript.json.trace.json');original=read(reference/'transcript.json.trace.json')
            if actual!=expected or any(trace[k]!=original[k] for k in ['words','word_speaker_slots','speaker_turns','decoded_pcm_sha256']):raise ValueError('Refactor parity failed')
            if any(x['alignment']!='ctc_tokens' for x in trace['asr']):raise ValueError('Unexpected chunk fallback')
            truth=read(ROOT/entry['reference'])['transcript']
            quality_rows.append(c);old_cases.append(old[ident])
            cases.append(dict(audio_id=ident,reference_words=c['speaker_attributed']['reference_words'],
                normalized=c['text_metrics']['normalized'],speaker_attributed=c['speaker_attributed'],
                punctuation=c['text_metrics']['punctuation']['end_to_end'],
                der=c['der_details']['diarization error rate'],jer=c['jer'],reference_speakers=len({r['speaker_id'] for r in truth}),
                predicted_speakers=c['known_speakers_count'],source_and_refactor_payload_exact=True,
                full_rtf=c['full_rtf'],sampled_peak_pss_kib=c['sampled_peak_pss_kib']))
    text=summarize([c['text_metrics'] for c in quality_rows]);plain=summarize([c['text_metrics'] for c in old_cases])
    if len(cases)!=6:raise ValueError('Incomplete quality suite')
    count=sum(c['reference_words'] for c in cases);new_errors=sum(c['speaker_attributed']['errors'] for c in cases)
    plain_errors=sum(c['speaker_attributed']['errors'] for c in old_cases)
    rng=np.random.default_rng(42);indices=rng.integers(0,len(cases),(10000,len(cases)))
    weights=np.array([c['reference_words'] for c in cases]);deltas=np.array([a['speaker_attributed']['errors']-b['speaker_attributed']['errors'] for a,b in zip(cases,old_cases)])
    cp_ci=np.quantile(deltas[indices].sum(axis=1)/weights[indices].sum(axis=1),[.025,.975]).tolist()
    details=[c['der_details'] for c in quality_rows]
    der=sum(sum(c[k] for k in ['missed detection','false alarm','confusion']) for c in details)/sum(c['total'] for c in details)
    jer=sum(c['jer']*c['reference_speakers'] for c in cases)/sum(c['reference_speakers'] for c in cases)
    targets=[];payload=None;runtime=None
    for eid,previous in [('exp_0234','exp_0224'),('exp_0235','exp_0225'),('exp_0236','exp_0226')]:
        c=report(eid)['cases'][0];ident=c['audio_id'];directory=ROOT/'.audio-runs'/eid
        cfg=read(directory/'config.json');build=read(directory/'build-provenance.json')
        for path,digest in canonical_build['inputs'].items():
            if path.startswith('src/audio/') and build['inputs'].get(path)!=digest:raise ValueError('Host/device native source differs')
        if runtime is not None and runtime!=cfg['device_runtime_sha256']:raise ValueError('Target runtime changed')
        runtime=cfg['device_runtime_sha256']
        trace=read(directory/ident/'transcript.json.trace.json');actual=read(directory/ident/'transcript.json')
        value=dict(transcript=actual,**{k:trace[k] for k in ['words','word_speaker_slots','speaker_turns','decoded_pcm_sha256']})
        before_dir=ROOT/'.audio-runs'/previous/ident
        before_trace=read(before_dir/'transcript.json.trace.json')
        if actual!=read(before_dir/'transcript.json') or any(trace[k]!=before_trace[k] for k in ['words','word_speaker_slots','speaker_turns','decoded_pcm_sha256']):raise ValueError('Device refactor parity failed')
        if payload is not None and payload!=value:raise ValueError('Device repeat changed output')
        payload=value
        if not c['host_comparison']['source_pcm_exact']:raise ValueError('Different target source PCM')
        targets.append(dict(experiment=eid,wall_seconds=c['wall_seconds'],full_rtf=c['full_rtf'],sampled_peak_pss_kib=c['sampled_peak_pss_kib'],
            text_metrics=c['text_metrics'],speaker_attributed=c['speaker_attributed'],refactor_and_repeat_exact=True))
    controls=report('exp_0239')
    if not controls['passed']:raise ValueError('Controls failed')
    legacy_new=read(ROOT/'.audio-runs/exp_0240/ru-youtube-movie_podcast/transcript.json')
    if legacy_new!=read(ROOT/'.audio-runs/exp_0203/ru-youtube-movie_podcast/transcript.json'):raise ValueError('Legacy API output regressed')
    for c in report('exp_0243')['cases']:
        if not c['baseline_words_exact'] or not all(c['host_comparison'].values()):raise ValueError('Sanitizer parity failed')
    capacity=report('exp_0242');performance=report('exp_0241');punct=report('exp_0223')
    for path,digest in canonical_build['inputs'].items():
        if path.startswith('src/audio/') and sha256(ROOT/path)!=digest:raise ValueError('Source changed after measurements')
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],cases=cases,text_metrics=text,
        normalized=text['normalized'],cer=text['normalized_cer']['cer'],cpwer=new_errors/count,der=der,jer=jer,
        previous_plain_ctc=dict(text_metrics=plain,cpwer=plain_errors/count),
        delta_cpwer=(new_errors-plain_errors)/count,paired_record_cpwer_delta_ci95=cp_ci,bootstrap_seed=42,
        punctuator_f1={k:v['punctuation']['end_to_end']['f1'] for k,v in punct['variants'].items()},
        targets=targets,median_target_full_rtf=statistics.median(c['full_rtf'] for c in targets),
        maximum_target_pss_kib=max(c['sampled_peak_pss_kib'] for c in targets),
        host_before_after_performance=performance,synthetic_capacity=capacity,controls_passed=True,legacy_json_exact=True,
        six_source_refactor_parity=True,sanitizer_full_model_smoke_passed=True,
        historical_phone40={eid:report(eid)['normalized'] for eid in ['exp_0078','exp_0079']},
        timestamp_mae_ms=None,arm_runtime_metrics=None,
        unavailable_reasons=dict(timestamp_mae='No independently annotated word times',arm_runtime='No physical ARM device; cross-build only',
            independent_dialogue_gold='Known publisher-reviewed silver only, speaker independence unverified'),
        limitation='Known six-record regression sample, not blind gold; selected punctuation/lexical tradeoff. Time/RAM are environment-specific. Synthetic capacity does not certify natural long-conversation quality.')
    report_dir=ROOT/'eval/results'/args.experiment;report_dir.mkdir(parents=True,exist_ok=False)
    for name,value in [('config.json',config),('metrics.json',metrics)]:
        (out/name).write_text(json.dumps(value,indent=2));(report_dir/name).write_bytes((out/name).read_bytes())
    print(json.dumps({k:metrics[k] for k in ['cpwer','der','jer','median_target_full_rtf','maximum_target_pss_kib','six_source_refactor_parity']}),flush=True)


if __name__=='__main__':main()
