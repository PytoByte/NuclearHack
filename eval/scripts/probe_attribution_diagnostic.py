#!/usr/bin/env python3
"""Diagnostic: localize where ASR/text errors are born (p.1 in user priority)."""
import argparse, json, os, re, difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def norm(t):
    return [w for w in re.split(r'\s+', ''.join(c.lower() if c.isalnum() else ' ' for c in t).replace('ё','е')) if w]

def align(a, b):
    m = difflib.SequenceMatcher(None, a, b)
    S = D = I = 0
    for tag,i1,i2,j1,j2 in m.get_opcodes():
        if tag == 'replace':
            S += max(i2-i1, j2-j1)
        elif tag == 'delete':
            D += i2-i1
        elif tag == 'insert':
            I += j2-j1
    M = m.ratio() * 100
    return S, D, I, M

def per_file(aid, exp, is_pilot=True):
    trace_path = ROOT/'.audio-runs'/exp/aid/'transcript.json.trace.json'
    final_path = ROOT/'.audio-runs'/exp/aid/'transcript.json'
    if not trace_path.exists():
        print('NO TRACE', trace_path); return None
    t = json.load(open(trace_path))
    asr_text = ' '.join(fr['backend'].get('text','') for fr in t['asr'])
    words = t.get('words', [])
    word_text = ' '.join(w.get('text','') for w in words)
    final = json.load(open(final_path)) if final_path.exists() else {'transcript': []}
    final_text = ' '.join(x.get('text','') for x in final.get('transcript', []))

    print('='*80)
    print('FILE', aid)
    print('  ASR frames      :', len(t['asr']))
    print('  words count     :', len(words))
    print('  final turns     :', len(final.get('transcript', [])), 'speakers:', sorted({x.get('speaker_id') for x in final.get('transcript', [])}))

    rt = norm(asr_text)
    wt = norm(word_text)
    ft = norm(final_text)

    # ASR frame-level first/last seaming
    print('  --- ASR frame seams ---')
    for i, fr in enumerate(t['asr']):
        txt = fr['backend'].get('text','')
        if i > 0:
            prev = t['asr'][i-1]['backend'].get('text','')
            last2 = prev[-15:]
            first2 = txt[:15]
            seam = ''
            if last2 and first2 and last2[-1:]==first2[:1] or last2[-3:] and first2[:3] and last2[-2:] == first2[:2]:
                seam = ' [possible seam dup]'
            print(f'    frame {i}: len={len(txt):4d} head={txt[:40]!r} tail={txt[-40:]!r}{seam}')

    # Anomalies in word list
    doubled = [w['text'] for w in words if any(w['text'][i]==w['text'][i-1] for i in range(1,len(w['text'])))]
    print('  doubled-letter words:', len(doubled), doubled[:12])

    # Word count mismatch ASR vs words
    print('  words/ASR token ratio words=', len(wt), 'ASR text norm=', len(rt))

    # top "extra letter" suspicious patterns: consecutive same first char token begins
    suspicious = [w for w in words if len(w['text']) >= 2 and w['text'][0]*2 == w['text'][:2]]
    print('  repeated-first-char words:', len(suspicious), [w['text'] for w in suspicious[:12]])

    # seam dup scan between adjacent frames
    seam_dups = 0
    frame_texts = [f['backend'].get('text','') for f in t['asr']]
    for i in range(1, len(frame_texts)):
        if frame_texts[i-1] and frame_texts[i] and (len(frame_texts[i-1]) > 4 and frame_texts[i][:4] == frame_texts[i-1][-4:]):
            seam_dups += 1
            if seam_dups <= 5:
                print(f'  SEAM DUP at frame {i}: ...{frame_texts[i-1][-20:]!r} | {frame_texts[i][:20]!r}')
    print('  seam candidate count:', seam_dups)

    s_d, d_d, i_d, ratio = align(wt, ft)
    print(f'  WER(words→final) ≈ S/D/I: {s_d}/{d_d}/{i_d} (ratio {ratio:.1f})')
    # ASR text vs words token diff
    s_a, d_a, i_a, r_a = align(rt, wt)
    print(f'  WER(asr_text→words) S/D/I: {s_a}/{d_a}/{i_a} (words alignment, ratio {r_a:.1f})')

    # final top tokens
    print('  FINAL tokens:')
    for x in final.get('transcript', [])[:4]:
        print(f'    [{x["start_ms"]}-{x["end_ms"]}ms] {x["speaker_id"]}: {x["text"][:70]!r}')
    return [aid, len(doubled), len(suspicious), seam_dups, s_d, d_d, i_d, s_a, d_a, i_a]
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exp', default='exp_0255')
    ap.add_argument('--files', nargs='+', default=['ru-youtube-yCX4MRy14zw', 'ru-youtube-p0_iIC13bs8', 'ru-youtube-nr3hmL9bcPU'])
    args = ap.parse_args()
    summary = []
    for fid in args.files:
        r = per_file(fid, args.exp)
        if r:
            summary.append(r)
    print('\nSUMMARY (per file):')
    print('audio_id | doubled | repeated-first-char | seam-dups | (words→final) S/D/I | (asr→words) S/D/I')
    for r in summary:
        print(f'{r[0]} | {r[1]} / {r[2]} / {r[3]} | {r[4]}/{r[5]}/{r[6]} | {r[7]}/{r[8]}/{r[9]}')

if __name__ == '__main__':
    main()