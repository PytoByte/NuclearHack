#!/usr/bin/env python3
"""600s capacity soak using repeated local PCM; no quality ground truth claim."""
import argparse
import json
import re
import sys
import wave
import numpy as np
from native_sdk import ROOT, NativeSdk, record_build
from run_file_pipeline import profile
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256
from audio_tools import transcript as validate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True);args=p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    fixture=json.loads((ROOT/'eval/data/russian-conversation-movie-session.jsonl').read_text().splitlines()[0])
    source=ROOT/fixture['audio']
    if sha256(source)!=fixture['audio_sha256']:raise ValueError('Changed source')
    sdk=NativeSdk();pcm=sdk.decode(source,max_frames=180*16000+16)
    if len(pcm)>=180*16000+16:raise ValueError('Source budget')
    # Encode deliberately synthetic repeated PCM as ordinary signed16 WAV.
    # Quantization and repetition are declared; no original-source parity claim.
    data=(np.clip(pcm,-1,1)*32767).round().astype('<i2'); frames=600*16000
    audio=out/'repeated-600s.wav'
    with wave.open(str(audio),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        remaining=frames
        while remaining:
            part=data[:remaining];w.writeframes(part.tobytes());remaining-=len(part)
    del pcm,data,sdk
    preset=json.loads((ROOT/'config/audio-sdk-preset.json').read_text())
    lock=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    chosen=[m for m in lock['models'] if m['id'] in [preset['asr'],preset['diarization']]]
    paths={p for m in chosen for p in m.get('runtime_files',m['files'])}
    files=[f for f in lock['files'] if f['path'] in paths]
    for f in files:
        if sha256(ROOT/f['path'])!=f['sha256']:raise ValueError('Changed selected model')
    config=dict(vars(args),preset=preset,model_files=files,source_audio_sha256=sha256(source),
      generated_audio_sha256=sha256(audio),sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),
      scope='host600s synthetic repeated-source capacity soak; no ASR/diarization quality labels, no hour/ARM certification')
    record_build(out,config);(out/'config.json').write_text(json.dumps(config,indent=2))
    asr=next(p for p in paths if p.endswith('model.int8.onnx'));tokens=next(p for p in paths if p.endswith('tokens.txt'))
    speaker=next(p for p in paths if p.endswith('model_quantized.onnx'))
    result=out/'transcript.json'
    command=[str(ROOT/'.build/audio/nh-audio'),'transcribe-final',str(audio),str(result),str(ROOT/asr),str(ROOT/tokens),str(ROOT/speaker),str(out),'4','600']
    timing=profile(command,out)
    if timing['exit_code']:raise RuntimeError('600s soak failed; logs retained')
    actual=json.loads(result.read_text());validate(actual)
    trace=json.loads((out/'transcript.json.trace.json').read_text());stats=trace['speaker_stream']
    source_samples=json.loads((out/'stdout.log').read_text())['source_samples']
    if source_samples!=frames or stats['emitted_frames']!=60000:raise ValueError('Source/emission grid mismatch')
    if stats['peak_buffered_samples']>486641:raise ValueError('Buffered speaker PCM bound exceeded')
    if any(not 0<=w['start_ms']<w['end_ms']<=600000 for w in trace['words']):raise ValueError('Word source bounds')
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],**timing,audio_seconds=600,
      source_samples=source_samples,inference_rtf=timing['wall_seconds']/600,native_stream=stats,
      words=len(trace['words']),json_valid=True,source_bounds_valid=True,
      ctc_chunk_fallbacks=sum(c['alignment']=='chunk_fallback' for c in trace['asr']),
      normalized_wer=None,cpwer=None,timestamp_mae_ms=None,
      limitation='Repeated/quantized input validates600s resource/control execution only; no independent quality, natural long-conversation speaker stability or timestamp accuracy measurement.')
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name,obj in [('config.json',config),('metrics.json',metrics)]:
        (out/name).write_text(json.dumps(obj,indent=2));(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics),flush=True)


if __name__=='__main__':main()
