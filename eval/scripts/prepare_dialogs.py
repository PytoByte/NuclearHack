#!/usr/bin/env python3
"""Russian structural MP3 smoke fixtures from licensed acted speech, not natural meetings."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np
import pyarrow.parquet as pq
from native_sdk import NativeSdk, ROOT
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap_models import fetch, sha256

REV = 'a74ff44d8d27ca3d21098ea3ed4d31a32923fbdd'
SOURCE = 'https://huggingface.co/datasets/langswap/dialogs-ru-emotional-conversations'


def main():
    source = ROOT / '.tools/datasets/dialogs-preview.parquet'
    fetch(f'{SOURCE}/resolve/{REV}/preview.parquet', source,
          'fba7215964aee4da95fe412d5ff434a912fe961be10b5eff6e9a9af49a315add')
    rows = pq.read_table(source).to_pylist()
    sdk = NativeSdk()
    source_dir = ROOT / 'eval/data/audio/dialogs-source'
    source_dir.mkdir(parents=True, exist_ok=True)
    samples = {}
    for index, row in enumerate(rows):
        path = source_dir / f'{index:03d}.wav'
        path.write_bytes(row['audio']['bytes'])
        samples[index] = sdk.decode(path)
    def choose(speaker, short=False):
        candidates = [i for i, r in enumerate(rows) if r['speaker_id'] == speaker and
                      (len(samples[i]) > 0 if short else 3 <= len(samples[i]) / 16000 <= 15)]
        return min(candidates, key=lambda i: len(samples[i])) if short else candidates[0]
    m, d, s = (choose(actor) for actor in ('M', 'D', 'S'))
    ms, ds, ss = (choose(actor, True) for actor in ('M', 'D', 'S'))
    cases = [('clean_2', [m, d, m, d], 0.4, 0, None),
             ('pauses_short_3', [ms, ds, ss, ms, ds, ss], 2.0, 0, None),
             ('noise_overlap_3', [m, d, s, m, d, s], 0.3, 0.35, 15.0)]
    manifest = []
    for name, indices, gap, overlap, snr in cases:
        audio_id = 'dialogs-' + name
        cursor = int(0.3 * 16000)
        placements = []
        for j, i in enumerate(indices):
            if j:
                cursor += int(gap * 16000) if not overlap or j % 2 == 0 else -int(overlap * 16000)
            placements.append((i, cursor, cursor + len(samples[i])))
            cursor += len(samples[i])
        mixed = np.zeros(cursor + 8000, dtype=np.float32)
        reference = []
        for i, start, end in placements:
            mixed[start:end] += samples[i]
            reference.append(dict(speaker_id=rows[i]['speaker_id'], start_ms=start * 1000 // 16000,
                end_ms=end * 1000 // 16000, text=rows[i]['text'].strip(), source_row=i,
                emotion=rows[i]['emotion'], source_sha256=hashlib.sha256(rows[i]['audio']['bytes']).hexdigest()))
        if snr is not None:
            noise = np.random.default_rng(42).normal(size=len(mixed)).astype(np.float32)
            rms = np.sqrt(np.mean(mixed * mixed))
            mixed += noise * rms / (10 ** (snr / 20))
        peak = float(np.max(np.abs(mixed)))
        if peak > 0.98:
            mixed *= 0.98 / peak
        wav = ROOT / 'eval/data/audio' / (audio_id + '.wav')
        mp3 = wav.with_suffix('.mp3')
        with wave.open(str(wav), 'wb') as out:
            out.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            out.writeframes((mixed * 32767).astype('<i2').tobytes())
        subprocess.run([str(ROOT / '.tools/bin/ffmpeg'), '-v', 'error', '-y', '-i', str(wav),
                        '-ar', '44100', '-codec:a', 'libmp3lame', '-q:a', '4', str(mp3)], check=True)
        ref = ROOT / 'eval/data/references' / (audio_id + '.json')
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(json.dumps(dict(transcript=reference), ensure_ascii=False, indent=2))
        manifest.append(dict(audio_id=audio_id, audio=str(mp3.relative_to(ROOT)),
            reference=str(ref.relative_to(ROOT)), audio_sha256=sha256(mp3), reference_sha256=sha256(ref),
            source=SOURCE, revision=REV, license='OpenRAIL (Dialogs license v1.1)',
            domain='acted Russian utterances reassembled for structural smoke; not natural meeting',
            speakers=len({r['speaker_id'] for r in reference}), gap_seconds=gap,
            overlap_seconds=overlap, additive_noise_snr_db=snr, noise_seed=42,
            timing_reference='source utterance placement incl. internal silence; not word alignment/true speech RTTM'))
    path = ROOT / 'eval/data/dialogs-smoke.jsonl'
    encoded = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in manifest)
    if path.exists() and path.read_text() != encoded:
        raise ValueError('Frozen fixture manifest changed; create a new dataset version')
    path.write_text(encoded)
    print(json.dumps(dict(manifest=str(path.relative_to(ROOT)), cases=[r['audio_id'] for r in manifest])))


if __name__ == '__main__':
    main()
