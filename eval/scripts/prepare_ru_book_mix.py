#!/usr/bin/env python3
"""Download and freeze a stratified RESEARCH corpus from mexus/ru-book-mix-10h (CC-BY-4.0).

CC-BY-4.0 (commercial OK). Each clip is 60s of synthetic multi-speaker
read-speech (1 or 2 voices, some with overlap up to ~12%) with RTTM GT.

This bundle is DIARIZATION-ONLY — no transcripts, so WER/cpWER/punctuation
cannot be computed, only DER/JER/speaker count and RTF/PSS.

Downloading ~1-2GB of shards anyway. With no network, download is skipped and
shards must be placed in .tools/datasets manually.
"""
import argparse, json, os, random, subprocess, sys, tarfile, tempfile
from pathlib import Path
from native_sdk import ROOT
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256

REPO = 'mexus/ru-book-mix-10h'
REV  = '18655c48833c5acfcd868a36eb38465712d15f1c'
SHARDS = ['shard-0000.tar','shard-0001.tar','shard-0002.tar','shard-0003.tar']

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shards', type=int, default=2, help='number of shards to download (default 2)')
    ap.add_argument('--count', type=int, default=50, help='number of clips to select')
    ap.add_argument('--mono-fraction', type=float, default=0.5)
    ap.add_argument('--min-speech', type=float, default=0.9)
    ap.add_argument('--seed', type=int, default=20261108)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    cache = ROOT/'.tools/datasets/ru-book-mix'
    cache.mkdir(parents=True, exist_ok=True)

    shards = list(range(args.shards))
    tar_paths = []
    for idx in shards:
        shard_name = SHARDS[idx]
        print('downloading shard', idx, flush=True)
        from huggingface_hub import hf_hub_download
        p = hf_hub_download(repo_id=REPO, filename='data/'+shard_name, repo_type='dataset', cache_dir=str(cache))
        tar_paths.append(p)

    # First pass: collect per-file metadata and RTTM from shards
    candidates = {}  # file_id -> (shard_path, json, flac member, rttm member)
    for tar_path in tar_paths:
        with tarfile.open(tar_path) as tf:
            members = {m.name: m for m in tf.getmembers()}
            found = {}
            for name in members:
                base = Path(name).stem
                if name.endswith('.json'):
                    found.setdefault(base, {})['json'] = name
                elif name.endswith('.flac'):
                    found.setdefault(base, {})['flac'] = name
                elif name.endswith('.rttm'):
                    found.setdefault(base, {})['rttm'] = name
            for base, parts in found.items():
                if not all(k in parts for k in ('json','flac','rttm')):
                    continue
                j = json.loads(tf.extractfile(parts['json']).read().decode())
                if j.get('duration', 0) < 55 or j.get('n_speakers') not in (1,2):
                    continue
                if j.get('overlap_stats', {}).get('speech', 0) < args.min_speech:
                    continue
                candidates[base] = (tar_path, parts['flac'], parts['rttm'], j)

    print('eligible clips total', len(candidates))

    # Stratified selection by mono (n_speakers=1) vs overlap (n_speakers=2 or overlap2>0)
    mono_pool = [b for b,j in candidates.items() if j[3]['n_speakers'] == 1]
    multi_pool = [b for b,j in candidates.items()
                  if j[3]['n_speakers'] == 2 or j[3].get('overlap_stats', {}).get('overlap2', 0) > 0]
    n_mono = int(args.count*args.mono_fraction)
    n_multi = args.count - n_mono
    chosen = (rng.sample(mono_pool, min(n_mono, len(mono_pool))) +
              rng.sample(multi_pool, min(n_multi, len(multi_pool))))

    out_audio = ROOT/'eval/data/audio'
    out_ref = ROOT/'eval/data/references'
    out_audio.mkdir(parents=True, exist_ok=True)
    out_ref.mkdir(parents=True, exist_ok=True)
    manifest = []

    for base in chosen:
        tar_path, flac_member, rttm_member, j = candidates[base]
        ident = f'rbm-{base}'
        wav_out = out_audio/(f'{ident}.wav')
        rttm_out = out_ref/(f'{ident}.rttm')
        if not wav_out.exists():
            import tempfile
            # extract flac to temp then ffmpeg
            with tarfile.open(tar_path) as tf:
                extracted_flac = tf.extractfile(flac_member).read()
            with tempfile.NamedTemporaryFile(suffix='.flac', delete=False) as tmp:
                tmp.write(extracted_flac)
                flac_path = tmp.name
            subprocess.run([str(ROOT/'.tools/bin/ffmpeg'), '-v', 'error', '-i', flac_path,
                            '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(wav_out)],
                           check=True)
            os.unlink(flac_path)
        if not rttm_out.exists():
            with tarfile.open(tar_path) as tf:
                rttm_bytes = tf.extractfile(rttm_member).read()
            # normalize speaker ids to consistent format
            rttm_text = rttm_bytes.decode()
            rttm_out.write_text(rttm_text)
        # Build reference JSON from RTTM for DER/JER scoring.
        ref_out = out_ref/(f'{ident}.json')
        if not ref_out.exists():
            turns = []
            for line in rttm_out.read_text().splitlines():
                parts = line.split()
                if len(parts) < 8 or parts[0] != 'SPEAKER':
                    continue
                start_s = float(parts[3]); dur_s = float(parts[4])
                speaker = parts[7]
                turns.append({'speaker_id': speaker, 'start_ms': round(start_s*1000), 'end_ms': round((start_s+dur_s)*1000), 'text': ''})
            ref_out.write_text(json.dumps({'transcript': turns}, ensure_ascii=False, indent=2)+'\n')
        sha_wav = sha256(wav_out)
        sha_rttm = sha256(rttm_out)
        sha_ref = sha256(ref_out)
        n_speakers = j['n_speakers']
        has_overlap = j.get('overlap_stats', {}).get('overlap2', 0) > 0
        manifest.append({
            'audio_id': ident,
            'audio': str(wav_out.relative_to(ROOT)),
            'rttm': str(rttm_out.relative_to(ROOT)),
            'reference': str(ref_out.relative_to(ROOT)),
            'audio_sha256': sha_wav,
            'rttm_sha256': sha_rttm,
            'reference_sha256': sha_ref,
            'speakers': n_speakers,
            'audio_seconds': 60,
            'source': 'mexus/ru-book-mix-10h',
            'license': 'CC-BY-4.0 (commercial OK)',
            'has_overlap': has_overlap,
            'snr_db': j.get('snr_db'),
            'overlap_fraction': j.get('overlap_stats', {}).get('overlap2', 0),
            'split': 'ru-book-mix-research',
            'reference_quality': 'RTTM ground truth from synthetic mixing pipeline; single read-speech voices, not natural conversation',
            'speaker_disjoint_verified': False,
            'reference_quality_note': 'synthetic multi-speaker from audiobook readers; no manual ASR text; DER/JER only',
        })
        print('processed', ident)

    out = ROOT/'eval/data'/'ru-book-mix-60.jsonl'
    out.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in manifest))
    print('wrote', len(manifest), 'rows to', out)

if __name__ == '__main__':
    main()