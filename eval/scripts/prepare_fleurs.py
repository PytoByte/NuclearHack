#!/usr/bin/env python3
"""Freeze a deterministic small read-speech screening set, never called by SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import fetch, sha256

REVISION = '70bb2e84b976b7e960aa89f1c648e09c59f894dd'
SPLITS = {
    'validation': ('21ff4b967df7be93985f8b2e51bebfd633ccfc7844cbc2b2e204e33e04bc9150', 40),
    'test': ('1e5bbee150c05a219c6c318e95d765886d34b4d179e8ab06dbecdb2791ac9a5d', 40),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=SPLITS, default='validation')
    args = parser.parse_args()
    checksum, count = SPLITS[args.split]
    source = ROOT / '.tools/datasets' / f'fleurs-ru-{args.split}.parquet'
    url = f'https://huggingface.co/datasets/google/fleurs/resolve/{REVISION}/parquet-data/ru_ru/{args.split}-00000-of-00001.parquet'
    fetch(url, source, checksum)
    parquet = pq.ParquetFile(source)
    metadata = parquet.read(columns=['id', 'path', 'num_samples', 'gender']).to_pylist()
    candidates = [(i, row) for i, row in enumerate(metadata) if 16000 <= row['num_samples'] <= 25 * 16000]
    # Freeze selection before inference; no WER-based filtering. Equal gender counts.
    selected = set()
    for gender in (0, 1):
        group = sorted((i for i, r in candidates if r['gender'] == gender),
                       key=lambda i: hashlib.sha256(('nuclear-v1:' + Path(metadata[i]['path']).name).encode()).hexdigest())
        selected.update(group[:count // 2])
    if len(selected) != count:
        raise ValueError('Insufficient eligible audio in dataset split')
    manifest = []
    offset = 0
    for batch in parquet.iter_batches(batch_size=32):
        for j, row in enumerate(batch.to_pylist()):
            if offset + j not in selected:
                continue
            audio_id = f'fleurs-ru-{args.split}-{offset + j:04d}'
            audio = ROOT / 'eval/data/audio' / (audio_id + '.wav')
            reference = ROOT / 'eval/data/references' / (audio_id + '.txt')
            audio.parent.mkdir(parents=True, exist_ok=True)
            reference.parent.mkdir(parents=True, exist_ok=True)
            data = row['audio']['bytes']
            if not data or data[:4] != b'RIFF':
                raise ValueError('Expected embedded WAV audio')
            audio.write_bytes(data)
            reference.write_text(row['raw_transcription'], encoding='utf-8')
            manifest.append(dict(audio_id=audio_id, audio=str(audio.relative_to(ROOT)),
                reference=str(reference.relative_to(ROOT)), audio_sha256=sha256(audio),
                reference_sha256=sha256(reference), source_id=row['id'],
                source_filename=Path(row['path']).name, num_samples=row['num_samples'],
                gender=row['gender'], split=args.split, domain='read-speech',
                source='google/fleurs ru_ru', revision=REVISION, license='CC-BY-4.0'))
        offset += batch.num_rows
    path = ROOT / 'eval/data' / f'fleurs-ru-{args.split}.jsonl'
    encoded = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in manifest)
    if path.exists() and path.read_text() != encoded:
        raise ValueError('Existing frozen manifest differs; use a new dataset version')
    path.write_text(encoded)
    print(json.dumps(dict(manifest=str(path.relative_to(ROOT)), selected=len(manifest),
        dataset_rows=len(metadata), eligible=len(candidates), manifest_sha256=sha256(path))))


if __name__ == '__main__':
    main()
