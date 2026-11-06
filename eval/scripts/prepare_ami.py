#!/usr/bin/env python3
"""Freeze one English AMI meeting excerpt for diarization smoke, not Russian ASR."""
import json
import argparse
import hashlib
import io
from pathlib import Path
import shutil
import sys
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import sha256, fetch

REVISION = '8cdaae2eaf968f3b000b6eb1204ab9b8db006ed0'
SOURCE_SHA = '50e2c8e4737850c4bf3cc24e7087c755e1c733cd91822106afd0df485ba64893'
API = 'https://datasets-server.huggingface.co/rows?dataset=diarizers-community/ami&config=ihm&split=test&offset=0&length=1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['test', 'validation'], default='test')
    args = parser.parse_args()
    if args.split == 'validation':
        import pyarrow.parquet as pq
        source = ROOT / '.tools/datasets/ami-ihm-validation.parquet'
        fetch(f'https://huggingface.co/datasets/diarizers-community/ami/resolve/{REVISION}/ihm/validation-00000-of-00003.parquet',
              source, '28c1344d598c6dde0dc9ffc95b740f21c28a8aea1fe975357b2ffdb44d449ae1')
        row = next(pq.ParquetFile(source).iter_batches(batch_size=1)).to_pylist()[0]
        data = row['audio']['bytes']
        audio_id = 'ami-ihm-validation-row0-first180'
        audio = ROOT / 'eval/data/audio' / (audio_id + '.wav')
        reference = ROOT / 'eval/data/references' / (audio_id + '.json')
        audio.parent.mkdir(parents=True, exist_ok=True)
        reference.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(io.BytesIO(data)) as src, wave.open(str(audio), 'wb') as target:
            if src.getnchannels() != 1 or src.getframerate() != 16000 or src.getsampwidth() != 2:
                raise ValueError('Unexpected AMI validation audio format')
            target.setparams(src.getparams())
            target.writeframes(src.readframes(180 * 16000))
        turns = [dict(start=max(0.0, start), end=min(180.0, end), speaker=speaker)
                 for start, end, speaker in zip(row['timestamps_start'], row['timestamps_end'], row['speakers'])
                 if end > 0 and start < 180 and end > start]
        reference.write_text(json.dumps(turns, indent=2))
        record = dict(audio_id=audio_id, audio=str(audio.relative_to(ROOT)), reference=str(reference.relative_to(ROOT)),
            audio_sha256=sha256(audio), reference_sha256=sha256(reference),
            source='diarizers-community/ami', source_revision=REVISION, source_split='validation',
            source_row=0, source_audio_sha256=hashlib.sha256(data).hexdigest(),
            excerpt_start_seconds=0, excerpt_end_seconds=180, license='CC-BY-4.0',
            language='English', domain='meeting IHM; calibration excerpt, not Russian')
        path = ROOT / 'eval/data/ami-diarization-validation.json'
        encoded = json.dumps(record, indent=2) + '\n'
        if path.exists() and path.read_text() != encoded:
            raise ValueError('Frozen validation manifest changed')
        path.write_text(encoded)
        print(json.dumps(dict(manifest=str(path.relative_to(ROOT)), turns=len(turns),
                              speakers=len({t['speaker'] for t in turns}))))
        return
    metadata = json.load(urllib.request.urlopen(API, timeout=60))
    row = metadata['rows'][0]['row']
    url = row['audio'][0]['src']
    if REVISION not in url:
        raise ValueError('AMI dataset revision changed; review and create a new frozen version')
    source = ROOT / '.tools/datasets/ami-ihm-test-row0.wav'
    if not source.exists() or sha256(source) != SOURCE_SHA:
        source.parent.mkdir(parents=True, exist_ok=True)
        temporary = source.with_suffix('.part')
        with urllib.request.urlopen(url, timeout=120) as stream, temporary.open('wb') as target:
            shutil.copyfileobj(stream, target)
        if sha256(temporary) != SOURCE_SHA:
            raise ValueError('AMI source audio hash differs')
        temporary.replace(source)
    audio = ROOT / 'eval/data/audio/ami-ihm-test-row0-first180.wav'
    reference = ROOT / 'eval/data/references/ami-ihm-test-row0-first180.json'
    audio.parent.mkdir(parents=True, exist_ok=True)
    reference.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(source)) as src, wave.open(str(audio), 'wb') as target:
        if src.getnchannels() != 1 or src.getframerate() != 16000 or src.getsampwidth() != 2:
            raise ValueError('Unexpected AMI audio format')
        target.setparams(src.getparams())
        target.writeframes(src.readframes(180 * 16000))
    turns = [dict(start=max(0.0, start), end=min(180.0, end), speaker=speaker)
             for start, end, speaker in zip(row['timestamps_start'], row['timestamps_end'], row['speakers'])
             if end > 0 and start < 180 and end > start]
    reference.write_text(json.dumps(turns, indent=2))
    result = dict(audio_id='ami-ihm-test-row0-first180', audio=str(audio.relative_to(ROOT)),
        reference=str(reference.relative_to(ROOT)), audio_sha256=sha256(audio), reference_sha256=sha256(reference),
        source='diarizers-community/ami', source_revision=REVISION, source_split='test',
        source_row=0, source_audio_sha256=SOURCE_SHA, excerpt_start_seconds=0, excerpt_end_seconds=180,
        license='CC-BY-4.0', language='English', domain='meeting IHM; diarization smoke only')
    manifest = ROOT / 'eval/data/ami-diarization-smoke.json'
    encoded = json.dumps(result, indent=2) + '\n'
    if manifest.exists() and manifest.read_text() != encoded:
        raise ValueError('Frozen AMI smoke manifest changed')
    manifest.write_text(encoded)
    print(json.dumps(dict(manifest=str(manifest.relative_to(ROOT)), reference_turns=len(turns),
                          reference_speakers=len({t['speaker'] for t in turns}))))


if __name__ == '__main__':
    main()
