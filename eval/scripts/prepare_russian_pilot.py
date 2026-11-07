#!/usr/bin/env python3
"""Freeze a conversational pilot from publisher-reviewed Label Studio annotations.

This is a silver reference, not independently verified verbatim/word alignment.
Session-separated files do not establish speaker-disjointness.
"""
import json
import argparse
import struct
import math
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

def wave_prefix(url,path,seconds=180):
    """A byte-range derivative, never represented as a complete source download."""
    if path.exists():return path
    def get(end):
        request=urllib.request.Request(url,headers={'Range':f'bytes=0-{end}'})
        with urllib.request.urlopen(request,timeout=120) as response:
            if response.status!=206 or not response.headers.get('Content-Range','').startswith('bytes 0-'):
                raise ValueError('Expected explicit source byte range')
            data=response.read(end+1)
            if len(data)!=end+1:raise ValueError('Incomplete audio prefix')
            return data
    header=get(65535)
    if header[:4]!=b'RIFF' or header[8:12]!=b'WAVE':raise ValueError('Expected RIFF WAV')
    pos=12;rate=align=None
    while pos+8<len(header):
        kind,size=struct.unpack_from('<4sI',header,pos)
        if kind==b'fmt ':
            fmt,channels,rate,byte_rate,align,bits=struct.unpack_from('<HHIIHH',header,pos+8)
            if fmt!=1 or channels!=2 or rate!=48000 or bits!=16:raise ValueError('Unexpected frozen movie WAV format')
        if kind==b'data':
            if rate is None:raise ValueError('Missing audio format')
            needed=pos+8+math.ceil(seconds*rate)*align
            data=get(needed-1)
            if data[:len(header)]!=header:raise ValueError('Source changed across range requests')
            path.write_bytes(data);return path
        pos+=8+size+(size%2)
    raise ValueError('WAV data not found in source header')

def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group();group.add_argument('--heldout-session',action='store_true');group.add_argument('--movie-session',action='store_true');args=parser.parse_args()
    tag='russian-conversation-movie-session' if args.movie_session else 'russian-conversation-heldout-session' if args.heldout_session else 'russian-conversation-pilot'
    cache=ROOT/'.tools/datasets/ru-youtube';cache.mkdir(parents=True,exist_ok=True)
    manifest=[];sources=[]
    filenames=['movie_podcast.json'] if args.movie_session else ['project-35-at-2025-05-08-20-14-e3016d43.json'] if args.heldout_session else ['youtube-1.json','youtube-2.json']
    for filename in filenames:
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
            if args.movie_session:source=wave_prefix(f'{SOURCE}/resolve/{REV}/{remote}',cache/'movie_podcast.first180s.wav.prefix')
            elif not source.exists():urllib.request.urlretrieve(f'{SOURCE}/resolve/{REV}/{remote}',source)
            sources.append(dict(path=remote,sha256=sha256(source)))
            if args.movie_session:sources[-1].update(source_file_complete=False,source_byte_range=[0,source.stat().st_size-1],full_source_bytes=1145098590)
            ident='ru-youtube-'+Path(remote).stem
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
                split='silver-session-holdout2' if args.movie_session else 'silver-session-holdout' if args.heldout_session else 'pilot-development',speaker_disjoint_verified=False,reference_quality='publisher-reviewed ASR silver; not independently verified verbatim; no word GT',
                annotation_lead_seconds=annotation.get('lead_time'),text_edits_vs_prediction=sum(texts[k]!=original[k] for k in texts.keys()&original.keys()),
                reviewed_turns=len(texts),domain='natural Russian YouTube interview/conversation',timing_reference='publisher turn boundaries; no independent manual accuracy audit'))
            if args.movie_session:manifest[-1].update(source_file_complete=False,source_byte_range=[0,source.stat().st_size-1],source_prefix_sha256=sha256(source))
    freeze(ROOT/'eval/data'/(tag+'.jsonl'),''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in manifest).encode())
    freeze(ROOT/'config'/(tag+'.lock.json'),(json.dumps(dict(source=SOURCE,revision=REV,files=sources,scope='silver session holdout; speaker independence unverified' if args.heldout_session or args.movie_session else 'silver pilot only; no Gate A or independent-test claim'),indent=2)+'\n').encode())
    print(json.dumps([dict(id=r['audio_id'],seconds=r['audio_seconds'],speakers=r['speakers'],edited=r['text_edits_vs_prediction']) for r in manifest]))

if __name__=='__main__':main()
