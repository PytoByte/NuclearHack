#!/usr/bin/env python3
"""Frozen codec/noise pairs and repeated-speech duration stress inputs, outside task/."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave
import numpy as np
from native_sdk import ROOT,NativeSdk,PCM
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


def immutable_manifest(path,rows):
    text=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)
    if path.exists() and path.read_text()!=text:raise ValueError('Frozen variant changed; use a new version tag')
    path.write_text(text)


def verify_existing(path):
    if not path.exists():return False
    for row in (json.loads(l) for l in path.read_text().splitlines()):
        if sha256(ROOT/row['audio'])!=row['audio_sha256']:raise ValueError('Changed frozen variant')
    print('Verified existing '+str(path.relative_to(ROOT)),flush=True);return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('kind',choices=['mp3_44k','wav_48k','noise15','noise15_denoise','long'])
    p.add_argument('--tag',default='v1');p.add_argument('--seconds',nargs='+',type=int,default=[300,900,1800,3600])
    args=p.parse_args()
    if not args.tag.replace('-','').isalnum():p.error('Use alphanumeric version tag')
    manifest=ROOT/'eval/data'/('dialogs-long-'+args.tag+'.jsonl' if args.kind=='long' else 'fleurs-'+args.kind+'-'+args.tag+'.jsonl')
    if verify_existing(manifest):return
    sdk=NativeSdk();ffmpeg=ROOT/'.tools/bin/ffmpeg'
    destination=ROOT/'eval/data/audio/variants'/(args.kind+'-'+args.tag);destination.mkdir(parents=True,exist_ok=True)
    def publish(temporary,path):
        if path.exists():
            if sha256(path)!=sha256(temporary):raise ValueError('Refuse overwriting existing audio variant')
        else:shutil.copyfile(temporary,path)
    def frames(path):
        count=0
        @PCM
        def consume(samples,n,offset,user):
            nonlocal count
            count+=n;return 0
        sdk.check(sdk.lib.nh_decode_file(str(path).encode(),16000,16000,consume,None));return count
    rows=[]
    if args.kind=='long':
        source=ROOT/'eval/data/audio/dialogs-clean_2.wav'
        for seconds in args.seconds:
            if seconds not in (300,900,1800,3600):raise ValueError('Use preregistered 5/15/30/60min stress durations')
            audio_id=f'dialogs-long-{seconds}';output=destination/(audio_id+'.mp3')
            with tempfile.TemporaryDirectory(dir=destination) as tmp:
                temp=Path(tmp)/'audio.mp3'
                subprocess.run([str(ffmpeg),'-v','error','-stream_loop','-1','-i',str(source),'-t',str(seconds),
                    '-ar','44100','-ac','1','-codec:a','libmp3lame','-q:a','4',str(temp)],check=True)
                publish(temp,output)
            n=frames(output)
            rows.append(dict(audio_id=audio_id,audio=str(output.relative_to(ROOT)),audio_sha256=sha256(output),
                num_samples=n,requested_seconds=seconds,speakers=2,source_sha256=sha256(source),
                source='langswap/dialogs-ru-emotional-conversations',license='OpenRAIL / source fixture license',
                domain='Repeated acted speech duration/memory stress, not natural meeting or new ASR quality evidence',
                ffmpeg_sha256=sha256(ffmpeg)))
    else:
        parent=ROOT/'eval/data/fleurs-ru-validation.jsonl'
        if args.kind=='noise15_denoise':
            parent=ROOT/'eval/data'/('fleurs-noise15-'+args.tag+'.jsonl')
            if not parent.exists():raise ValueError('Prepare noise15 first')
        for original in (json.loads(l) for l in parent.read_text().splitlines()):
            source=ROOT/original['audio']
            if sha256(source)!=original['audio_sha256']:raise ValueError('Changed source audio')
            extension='.mp3' if args.kind=='mp3_44k' else '.wav'
            output=destination/(original['audio_id']+extension)
            transform=dict(kind=args.kind,version=args.tag,source_sha256=original['audio_sha256'],ffmpeg_sha256=sha256(ffmpeg))
            with tempfile.TemporaryDirectory(dir=destination) as tmp:
                temp=Path(tmp)/('audio'+extension)
                if args.kind=='noise15':
                    clean=sdk.decode(source);seed=(int(original['audio_sha256'][:8],16)^42)
                    noise=np.random.default_rng(seed).normal(size=len(clean)).astype(np.float32)
                    noise*=float(np.sqrt(np.mean(clean*clean)))/(10**(15/20)*float(np.sqrt(np.mean(noise*noise))))
                    mixed=clean+noise;gain=min(1.0,.98/float(np.max(np.abs(mixed))))
                    with wave.open(str(temp),'wb') as target:
                        target.setparams((1,2,16000,0,'NONE','not compressed'))
                        target.writeframes(np.rint(mixed*gain*32767).astype('<i2').tobytes())
                    transform.update(snr_db=15,seed=seed,headroom_gain=gain)
                else:
                    options={'mp3_44k':['-ar','44100','-codec:a','libmp3lame','-q:a','4'],
                        'wav_48k':['-ar','48000','-codec:a','pcm_s16le'],
                        'noise15_denoise':['-af','afftdn=nf=-35:tn=1','-ar','16000','-codec:a','pcm_s16le']}[args.kind]
                    subprocess.run([str(ffmpeg),'-v','error','-i',str(source),'-ac','1',*options,str(temp)],check=True)
                    if args.kind=='noise15_denoise':transform['filter']='afftdn=nf=-35:tn=1'
                publish(temp,output)
            row=dict(original,audio=str(output.relative_to(ROOT)),audio_sha256=sha256(output),num_samples=frames(output),transform=transform)
            rows.append(row)
    immutable_manifest(manifest,rows)
    print(json.dumps(dict(manifest=str(manifest.relative_to(ROOT)),clips=len(rows),manifest_sha256=sha256(manifest))),flush=True)


if __name__=='__main__':main()
