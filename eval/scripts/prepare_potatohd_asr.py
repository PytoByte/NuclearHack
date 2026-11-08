#!/usr/bin/env python3
"""Importer for PotatoHD/ru-asr-dataset (research-only): spoken Russian monologues.

License: unspecified on the HF card -> DO NOT ship; tests/R&D only.
Audio is stored inline in Parquet as FLAC (48k? any sr), we decode to mono 16kHz.
Text is model-generated / web captions (not necessarily manual GT) -- use for
ASR WER/CER/punct trends, NOT as an independent gold benchmark.

Outputs:
  - eval/data/audio/potato-<id>.wav
  - eval/data/references/potato-<id>.json   (single turn 0..dur with `text`)
  - eval/data/potato-rus-asr.jsonl
  - eval/data/references/potato-<id>.words.json  (optional, their ASR word timestamps)
"""
import argparse, hashlib, json, os, random, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent/'scripts'))
from native_sdk import ROOT
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--split', choices=['validation','test','train'], default='validation')
    ap.add_argument('--limit', type=int, default=100)
    ap.add_argument('--seed', type=int, default=20261109)
    args = ap.parse_args()
    random.seed(args.seed)

    shard = 'validation-00000-of-00001.parquet' if args.split=='validation' else \
            'test-00000-of-00001.parquet' if args.split=='test' else 'train-00000-of-00019.parquet'
    repo = 'PotatoHD/ru-asr-dataset'
    print(f'downloading {repo}/{shard} (may be ~200MB)', flush=True)
    from huggingface_hub import hf_hub_download
    parquet_path = hf_hub_download(repo_id=repo, filename='data/'+shard, repo_type='dataset')

    import pyarrow.parquet as pq
    table = pq.read_table(parquet_path)
    rows = table.to_pandas().to_dict('records')
    print(f'{args.split}: {len(rows)} rows, sampling {min(args.limit,len(rows))}')
    sampled = random.sample(rows, min(args.limit, len(rows))) if args.limit > 0 else rows

    out_audio = ROOT/'eval/data/audio'
    out_ref   = ROOT/'eval/data/references'
    out_audio.mkdir(parents=True, exist_ok=True)
    out_ref.mkdir(parents=True, exist_ok=True)
    manifest = []
    skipped = 0
    for r in sampled:
        rid = r['id']
        ident = f'potato-{rid}'
        wav_out = out_audio/(f'{ident}.wav')
        ref_out = out_ref/(f'{ident}.json')
        words_out = out_ref/(f'{ident}.words.json')
        if not wav_out.exists():
            b = r['audio']['bytes']
            if not b:
                skipped += 1
                continue
            with tempfile.NamedTemporaryFile(suffix='.flac', delete=False) as tmp:
                tmp.write(b)
                flac_path = tmp.name
            try:
                subprocess.run([str(ROOT/'.tools/bin/ffmpeg'), '-v','error','-i',flac_path,
                                '-ar','16000','-ac','1','-c:a','pcm_s16le',str(wav_out)],
                               check=True)
            except subprocess.CalledProcessError:
                print('ffmpeg failed', ident); skipped+=1; os.unlink(flac_path); continue
            os.unlink(flac_path)
        if not ref_out.exists():
            dur = r['duration']
            text = r['text']
            turns = [{'speaker_id':'speaker_0','start_ms':0,'end_ms':round(dur*1000),'text':text}]
            ref_out.write_text(json.dumps({'transcript':turns}, ensure_ascii=False, indent=2)+'\n')
        if not words_out.exists():
            words = r.get('words') or {}
            words_out.write_text(json.dumps({'words':words,'speakers':r.get('speakers'),'turns':r.get('turns')}, ensure_ascii=False, indent=2, default=lambda o:o if isinstance(o,(tuple,list,dict)) else str(o))+'\n')
        manifest.append({
            'audio_id': ident,
            'audio': str(wav_out.relative_to(ROOT)),
            'reference': str(ref_out.relative_to(ROOT)),
            'audio_sha256': sha256(wav_out),
            'reference_sha256': sha256(ref_out),
            'speakers': 1,
            'audio_seconds': round(r['duration'],3),
            'source': 'PotatoHD/ru-asr-dataset',
            'license': 'research-only (license unspecified on card)',
            'language': r.get('language'),
            'duration': r['duration'],
            'source_id': r.get('raw_id'),
            'chunk_id': r.get('chunk_id'),
            'words_file': str(words_out.relative_to(ROOT)),
            'reference_quality': 'Model-generated transcript + ASR-side word timestamps; NOT manual gold',
            'speaker_disjoint_verified': False,
        })
        if len(manifest) % 10 == 0:
            print(f'  processed {len(manifest)}')
    out = ROOT/'eval/data'/f'potato-rus-asr-{args.split}.jsonl'
    out.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in manifest))
    print(f'wrote {len(manifest)} rows to {out}; skipped={skipped}')

if __name__ == '__main__':
    main()