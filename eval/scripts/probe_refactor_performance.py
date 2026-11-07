#!/usr/bin/env python3
"""Alternating archived/current native binaries, same models/input/host session."""
import argparse
import json
import re
import statistics
import sys
from native_sdk import ROOT, record_build
from run_file_pipeline import profile
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256
from audio_tools import transcript as validate


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',required=True);args=parser.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):parser.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    previous=json.loads((ROOT/'.audio-runs/exp_0221/build-provenance.json').read_text())
    old=ROOT/previous['artifact_directory'];current=ROOT/'.build/audio'
    if sha256(old/'libnuclear_audio.so')!=previous['sdk_sha256']:raise ValueError('Archived SDK changed')
    if sha256(old/'nh-audio')!=previous['executables']['nh-audio']:raise ValueError('Archived CLI changed')
    for path,digest in previous['runtime_libraries'].items():
        if sha256(old/path.split('/')[-1])!=digest:raise ValueError('Archived runtime changed')
    fixture=json.loads((ROOT/'eval/data/russian-conversation-movie-session.jsonl').read_text().splitlines()[0])
    if sha256(ROOT/fixture['audio'])!=fixture['audio_sha256']:raise ValueError('Changed input')
    baseline=ROOT/'.audio-runs/exp_0221'/fixture['audio_id']
    expected=json.loads((baseline/'transcript.json').read_text())
    trace=json.loads((baseline/'transcript.json.trace.json').read_text())
    paths=['models/giga-v3-ctc-punct/model.int8.onnx','models/giga-v3-ctc-punct/tokens.txt',
      'models/nemotron3-diarization/model_quantized.onnx','models/nemotron3-diarization/model_quantized.onnx_data']
    lock=json.loads((ROOT/'config/audio-models.lock.json').read_text());files=[f for f in lock['files'] if f['path'] in paths]
    for f in files:
        if sha256(ROOT/f['path'])!=f['sha256']:raise ValueError('Changed model')
    config=dict(vars(args),sdk_sha256=sha256(current/'libnuclear_audio.so'),model_files=files,
      old_provenance=previous,source_audio_sha256=fixture['audio_sha256'],order=['old','new','new','old','old','new'],
      scope='same-session alternating host full pipeline old/current native binary performance control; unisolated developer host, not ARM or cold-cache')
    record_build(out,config);(out/'config.json').write_text(json.dumps(config,indent=2))
    cases=[]
    for i,name in enumerate(config['order']):
        folder=out/(str(i)+'-'+name);folder.mkdir();output=folder/'transcript.json'
        if name=='old':
            command=['env','LD_LIBRARY_PATH='+str(old),str(old/'nh-audio'),'transcribe-stream',str(ROOT/fixture['audio']),str(output),*[str(ROOT/p) for p in paths[:3]],str(folder),'4','1','20','600']
        else:
            command=[str(current/'nh-audio'),'transcribe-final',str(ROOT/fixture['audio']),str(output),*[str(ROOT/p) for p in paths[:3]],str(folder),'4','600']
        (folder/'command.json').write_text(json.dumps(command,indent=2));timing=profile(command,folder)
        if timing['exit_code']:raise RuntimeError('Paired native run failed')
        actual=json.loads(output.read_text());validate(actual)
        current_trace=json.loads((folder/'transcript.json.trace.json').read_text())
        if actual!=expected or any(current_trace[k]!=trace[k] for k in ['words','word_speaker_slots','speaker_turns','decoded_pcm_sha256']):raise ValueError('Performance A/B changed quality output')
        cases.append(dict(variant=name,pair=i//2,**timing,audio_seconds=fixture['audio_seconds'],exact_output=True))
        print(json.dumps(cases[-1]),flush=True)
    pairs=[]
    for i in range(3):
        values={c['variant']:c for c in cases if c['pair']==i}
        pairs.append(values['new']['wall_seconds']/values['old']['wall_seconds'])
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],cases=cases,
      median_new_over_old_wall_ratio=statistics.median(pairs),pair_wall_ratios=pairs,
      variants={name:dict(median_wall_seconds=statistics.median(c['wall_seconds'] for c in cases if c['variant']==name),
        maximum_sampled_pss_kib=max(c['sampled_peak_pss_kib'] for c in cases if c['variant']==name)) for name in ['old','new']},
      limitation='Three alternating pairs, shared developer host; ratios are measured diagnostics, not an isolated CPU benchmark or a speedup guarantee.')
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name,value in [('config.json',config),('metrics.json',metrics)]:
        (out/name).write_text(json.dumps(value,indent=2));(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics['variants']),flush=True)


if __name__=='__main__':main()
