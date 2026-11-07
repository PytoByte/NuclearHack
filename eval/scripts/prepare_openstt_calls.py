#!/usr/bin/env python3
"""Popular OpenSTT manually annotated phone speech: deterministic lexical dev40.

No speaker identities, word timings, or reliable punctuation references are claimed.
The CC-BY-NC4.0 corpus is research data and is excluded from delivery artifacts.
"""
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import urllib.request
import wave
from pathlib import Path
from native_sdk import ROOT
from prepare_russian_pilot import freeze
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256

URL='https://zenodo.org/api/records/4899885/files/asr_calls_2_val.tar.gz/content'
MD5='5146eef0aa64af41e17c5ec18a9cab5c'

def main():
    archive=ROOT/'.tools/datasets/asr_calls_2_val.tar.gz'
    if not archive.exists():
        temporary=archive.with_suffix('.download');urllib.request.urlretrieve(URL,temporary);temporary.rename(archive)
    md5=hashlib.md5()
    with archive.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):md5.update(block)
    if md5.hexdigest()!=MD5:raise ValueError('OpenSTT source archive checksum differs')
    texts={};selected={};ranks={};total=0
    with tarfile.open(archive,'r|gz') as tar:
        for member in tar:
            if not member.isfile():continue
            suffix=Path(member.name).suffix;stem=str(Path(member.name).with_suffix(''))
            if suffix not in ('.wav','.txt'):continue
            data=tar.extractfile(member).read()
            if suffix=='.txt':texts[stem]=data.decode('utf-8').strip();continue
            total+=1
            with wave.open(io.BytesIO(data),'rb') as wav:duration=wav.getnframes()/wav.getframerate()
            if not 2<=duration<=20:continue
            rank=hashlib.sha256(stem.encode()).hexdigest()
            selected[stem]=(data,duration);ranks[stem]=rank
            # More candidates retained for the predeclared >=3-word filter.
            if len(selected)>160:
                worst=max(ranks,key=ranks.get);del selected[worst];del ranks[worst]
    choices=[stem for stem in sorted(ranks,key=ranks.get) if len(texts.get(stem,'').split())>=3][:40]
    if len(choices)!=40:raise ValueError('Insufficient phone examples')
    rows=[]
    for stem in choices:
        data,duration=selected[stem];ident='openstt-calls2-'+Path(stem).name
        source=ROOT/'.tools/datasets'/f'{ident}.wav';source.write_bytes(data)
        audio=ROOT/'eval/data/audio'/f'{ident}.wav';audio.parent.mkdir(parents=True,exist_ok=True)
        if not audio.exists():subprocess.run([str(ROOT/'.tools/bin/ffmpeg'),'-v','error','-i',str(source),'-ar','16000','-ac','1','-c:a','pcm_s16le',str(audio)],check=True)
        reference=ROOT/'eval/data/references'/f'{ident}.txt';freeze(reference,(texts[stem]+'\n').encode())
        with wave.open(str(audio),'rb') as wav:frames=wav.getnframes()
        rows.append(dict(audio_id=ident,audio=str(audio.relative_to(ROOT)),reference=str(reference.relative_to(ROOT)),
            audio_sha256=sha256(audio),reference_sha256=sha256(reference),num_samples=frames,sample_rate=16000,
            source='https://github.com/snakers4/open_stt',source_archive=URL,archive_md5=MD5,source_member=stem,
            source_audio_sha256=hashlib.sha256(data).hexdigest(),license='CC-BY-NC-4.0',split='validation-lexical-dev40',
            domain='real Russian phone calls; publisher manual transcripts',speaker_disjoint_verified=False,
            punctuation_reference_available=False,timestamp_reference_available=False))
    freeze(ROOT/'eval/data/openstt-calls-validation.jsonl',''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows).encode())
    freeze(ROOT/'config/openstt-calls.lock.json',(json.dumps(dict(url=URL,archive_md5=MD5,archive_sha256=sha256(archive),
        archive_size=archive.stat().st_size,selection='lowest SHA256(source stem),2..20s,>=3words,40of160 retained candidates',
        archive_audio_files=total,license='CC-BY-NC-4.0',scope='lexical dev only; no punctuation/speaker/time gold'),indent=2)+'\n').encode())
    print(json.dumps(dict(examples=len(rows),seconds=sum(r['num_samples']/16000 for r in rows))))

if __name__=='__main__':main()
