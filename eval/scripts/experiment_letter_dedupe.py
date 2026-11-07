#!/usr/bin/env python3
"""Quick A/B: strip duplicated leading letters on ASR tokens.

Pure postprocessing experiment: does removing doubled first-char tokens
(\"ЗЗдравствуйте\" -> \"Здравствуйте\") reduce WER on pilot?
"""
import argparse, json, os, re, difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = 'exp_0255'

def norm(t):
    return [w for w in re.split(r'\s+', ''.join(c.lower() if c.isalnum() else ' ' for c in t).replace('ё','е')) if w]

def wer(ref, hyp):
    m=difflib.SequenceMatcher(None, ref, hyp); S=D=I=0
    for tag,i1,i2,j1,j2 in m.get_opcodes():
        if tag=='replace': S+=max(i2-i1,j2-j1)
        elif tag=='delete': D+=i2-i1
        elif tag=='insert': I+=j2-j1
    refn=len(ref); n=S+D+I
    return n/refn if refn else 0.0, S,D,I,refn

def repair(text):
    # remove duplicated first char only if next token starts with different letter (e.g. ЗЗдрав -> Здрав)
    words = text.split()
    out=[]
    for w in words:
        if len(w)>=2 and w[0].isalpha() and w[1].isalpha() and w[0].lower()==w[1].lower() and (len(w)==2 or (w[2].isalpha() and w[2].lower()!=w[0].lower())):
            out.append(w[1:]); # drop one doubled leading letter
        else:
            out.append(w)
    return ' '.join(out)

def main():
    files=['ru-youtube-yCX4MRy14zw','ru-youtube-p0_iIC13bs8','ru-youtube-nr3hmL9bcPU']
    tot_base=0; tot_cand=0; tot_ref=0; totalSb=totalDb=totalIb=0; totalsc=totaldc=totalic=0
    for fid in files:
        trace_path=ROOT/'.audio-runs'/EXP/fid/'transcript.json.trace.json'
        t=json.load(open(trace_path))
        asr_text = ' '.join(fr['backend'].get('text','') for fr in t['asr'])
        ref_text = json.load(open(ROOT/'eval/data/references'/f'{fid}.json'))['transcript']
        ref_text = ' '.join(x['text'] for x in ref_text)
        cand_text = repair(asr_text)

        from difflib import SequenceMatcher
        m=difflib.SequenceMatcher(None, norm(ref_text), norm(asr_text))
        bs=bd=bi=0
        for tag,i1,i2,j1,j2 in m.get_opcodes():
            if tag=='replace': bs+=max(i2-i1,j2-j1)
            elif tag=='delete': bd+=i2-i1
            elif tag=='insert': bi+=j2-j1
        mr=difflib.SequenceMatcher(None, norm(ref_text), norm(cand_text))
        cs=cd_=ci=0
        for tag,i1,i2,j1,j2 in mr.get_opcodes():
            if tag=='replace': cs+=max(i2-i1,j2-j1)
            elif tag=='delete': cd_+=i2-i1
            elif tag=='insert': ci+=j2-j1
        R=len(norm(ref_text))
        print(f'{fid}: baseline { (bs+bd+bi)/R*100:6.2f}% (S{bs}D{bd}I{bi}); repaired { (cs+cd_+ci)/R*100:6.2f}% (S{cs}D{cd_}I{ci}); ref {R}')
        totalSb+=bs; totalDb+=bd; totalIb+=bi; totalsc+=cs; totaldc+=cd_; totalic+=ci; tot_ref+=R
    print('AGGREGATE baseline:', round((totalSb+totalDb+totalIb)/tot_ref*100,2))
    print('AGGREGATE repaired :', round((totalsc+totaldc+totalic)/tot_ref*100,2))

if __name__ == '__main__':
    main()