#!/usr/bin/env python3
"""Freeze a conversational pilot from publisher-reviewed Label Studio annotations.

This is a silver reference, not independently verified verbatim/word alignment.
Session-separated files do not establish speaker-disjointness.
"""
import json
import sys
import subprocess
import urllib.request
from pathlib import Path
from native_sdk import ROOT
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256

REV='e3aaa8a28211afe56c913fcacb26db029b1fb10e'
SOURCE='https://huggingface.co/datasets/leshinsky/ru-youtube-diarization'

def freeze(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_bytes()!=data:raise ValueError('Refusing to change frozen artifact '+str(path))
    path.write_bytes(data)

def main():
    cache=ROOT/'.tools/datasets/ru-youtube';cache.mkdir(parents=True,exist_ok=True)
    manifest=[];sources=[]
    for filename in ['youtube-1.json','youtube-2.json']:
        path=cache/filename
        if not path.exists():urllib.request.urlretrieve(f'{SOURCE}/resolve/{REV}/{filename}',path)
        sources.append(dict(path=filename,sha256=sha256(path)))
        for row in json.loads(path.read_text()):
            annotation=row['annotations'][0];results=annotation['result']
            labels={x['id']:x['value'] for x in results if x['type']=='labels'}
            texts={x['id']:' '.join(x['value']['text']).strip() for x in results if x['type']=='textarea'}
            original={x['id']:' '.join(x['value']['text']).strip() for x in annotation.get('prediction',{}).get('result',[]) if x['type']=='textarea'}
            candidates=sorted({v['end'] for v in labels.values() if v['end']<=180},reverse=True)
            end=next(e for e in candidates if not any(v['start']<e-1e-5 and v['end']>e+1e-5 for v in labels.values()))
            turns=[dict(speaker_id=v['labels'][0].replace(' ','_'),start_ms=round(v['start']*1000),end_ms=round(v['end']*1000),text=texts[k])
                   for k,v in labels.items() if v['end']<=end+1e-5 and texts.get(k)]
            turns.sort(key=lambda t:(t['start_ms'],t['end_ms']))
            remote=row['data']['audio'];source=cache/Path(remote).name
            if not source.exists():urllib.request.urlretrieve(f'{SOURCE}/resolve/{REV}/{remote}',source)
            sources.append(dict(path=remote,sha256=sha256(source)))
            ident='ru-youtube-'+source.stem
            wav=ROOT/'eval/data/audio'/f'{ident}.wav';wav.parent.mkdir(parents=True,exist_ok=True)
            if not wav.exists():subprocess.run([str(ROOT/'.tools/bin/ffmpeg'),'-v','error','-i',str(source),'-t',str(end),'-ar','16000','-ac','1','-c:a','pcm_s16le',str(wav)],check=True)
            ref=ROOT/'eval/data/references'/f'{ident}.json'
            freeze(ref,(json.dumps(dict(transcript=turns),ensure_ascii=False,indent=2)+'\n').encode())
            rttm=ref.with_suffix('.rttm')
            freeze(rttm, ''.join(f"SPEAKER {ident} 1 {t['start_ms']/1000:.3f} {(t['end_ms']-t['start_ms'])/1000:.3f} <NA> <NA> {t['speaker_id']} <NA> <NA>\n" for t in turns).encode())
            manifest.append(dict(audio_id=ident,audio=str(wav.relative_to(ROOT)),reference=str(ref.relative_to(ROOT)),
                audio_sha256=sha256(wav),reference_sha256=sha256(ref),rttm=str(rttm.relative_to(ROOT)),rttm_sha256=sha256(rttm),
                speakers=len({t['speaker_id'] for t in turns}),audio_seconds=end,source=SOURCE,revision=REV,source_audio=remote,
                source_annotation=filename,license='Apache-2.0 declared by publisher; underlying video provenance undocumented',
                split='pilot-development',speaker_disjoint_verified=False,reference_quality='publisher-reviewed ASR silver; not independently verified verbatim; no word GT',
                annotation_lead_seconds=annotation.get('lead_time'),text_edits_vs_prediction=sum(texts[k]!=original[k] for k in texts.keys()&original.keys()),
                reviewed_turns=len(texts),domain='natural Russian YouTube interview/conversation',timing_reference='publisher turn boundaries; no independent manual accuracy audit'))
    freeze(ROOT/'eval/data/russian-conversation-pilot.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in manifest).encode())
    freeze(ROOT/'config/russian-conversation-pilot.lock.json',(json.dumps(dict(source=SOURCE,revision=REV,files=sources,scope='silver pilot only; no Gate A or independent-test claim'),indent=2)+'\n').encode())
    print(json.dumps([dict(id=r['audio_id'],seconds=r['audio_seconds'],speakers=r['speakers'],edited=r['text_edits_vs_prediction']) for r in manifest]))

if __name__=='__main__':main()
