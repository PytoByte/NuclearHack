#!/usr/bin/env python3
"""Rebuild a compact experiment index from immutable measured reports."""
import argparse
import csv
import json
from pathlib import Path
from bootstrap_models import ROOT, sha256


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment'); p.add_argument('--status'); p.add_argument('--baseline'); p.add_argument('--changed')
    args = p.parse_args()
    path = ROOT / 'experiments/registry.csv'
    previous = {r['experiment_id']: r for r in csv.DictReader(path.open())}
    fields = ['experiment_id','date','scope','git_sha','config_sha256','model_sha256','model_lock_sha256','dataset_split',
        'hardware','seed','changed_parameter','baseline','wer','cer','der','rtf','peak_ram_kib',
        'crashes','status','metrics','logs','cpwer','jer','punctuation_wer','punctuation_f1','unknown_word_fraction','timestamp_mae_ms']
    rows = []
    for report in sorted((ROOT / 'eval/results').glob('exp_*')):
        eid = report.name
        m = read(report/'metrics.json'); c = read(report/'config.json')
        env = {**read(report/'dispatch-environment.json'), **read(report/'environment.json')}
        row = {f: previous.get(eid, {}).get(f, '') for f in fields}
        row.update(experiment_id=eid, date=row['date'] or '2026-11-07',
            git_sha=env.get('git_sha', row['git_sha']), scope=m.get('scope', row['scope']),
            hardware=c.get('abi', env.get('host', row['hardware'])),
            dataset_split=m.get('dataset_split', c.get('manifest',{}).get('source_split','') if isinstance(c.get('manifest'),dict) else c.get('manifest','')),
            config_sha256=sha256(report/'config.json') if (report/'config.json').exists() else '',
            metrics=str((report/('metrics.json' if m else 'failure.json')).relative_to(ROOT)),
            logs='.audio-runs/'+eid)
        # Model SHA entries must come from the recorded config, never today's lock.
        row['model_sha256'] = json.dumps({f['path']:f['sha256'] for f in c.get('model_files',[])},sort_keys=True) if c.get('model_files') else c.get('model_sha256','')
        row['model_lock_sha256'] = c.get('model_lock_sha256','')
        row['wer'] = m.get('normalized',{}).get('wer',m.get('normalized_wer',row['wer']))
        row['cer'] = m.get('cer',row['cer'])
        row['der'] = m.get('der_details',{}).get('diarization error rate',row['der'])
        cases=m.get('cases',[])
        attributed=[x['speaker_attributed'] for x in cases if 'speaker_attributed' in x and 'audio_id' in x]
        total_words=sum(x.get('reference_words',0) for x in attributed)
        if total_words:row['cpwer']=sum(x['errors'] for x in attributed)/total_words
        covered=[x for x in cases if 'unknown_word_fraction' in x and 'normalized' in x]
        def hypothesis_words(x):
            score=x['normalized'];return score['reference_words']-score['deletions']+score['insertions']
        covered_words=sum(hypothesis_words(x) for x in covered)
        if covered_words:row['unknown_word_fraction']=sum(x['unknown_word_fraction']*hypothesis_words(x) for x in covered)/covered_words
        row['jer']=m.get('jer',row['jer'])
        text=m.get('text_metrics',{})
        row['punctuation_wer']=text.get('punctuation_token_wer',{}).get('wer',row['punctuation_wer'])
        row['punctuation_f1']=text.get('punctuation',{}).get('end_to_end',{}).get('f1',row['punctuation_f1'])
        seconds=sum(x.get('audio_seconds',0) for x in cases)
        row['rtf'] = (sum(x.get('wall_ms',x.get('wall_seconds',0)*1000) for x in cases)/1000/seconds
                      if seconds else m.get('inference_rtf',row['rtf']))
        peaks=[m.get('process_peak_rss_kib',0)]
        for x in cases:
            peaks += [x.get('process_peak_rss_kib',0),x.get('process_lifetime_peak_rss_after_llm_kib',0),
                      x.get('process_lifetime_peak_rss_kib',0),x.get('summary',{}).get('process_peak_rss_kib',0)]
        if max(peaks):row['peak_ram_kib']=max(peaks)
        if (report/'invalidity.json').exists():
            row['status']='reject';row['scope']='INVALID decoded source length; see invalidity.json and replacement run'
        if (report/'failure.json').exists():row['status']=row['status'] or 'inconclusive'
        else:row['status']=row['status'] or 'unreviewed'
        if eid == args.experiment:
            for key,value in [('status',args.status),('baseline',args.baseline),('changed_parameter',args.changed)]:
                if value is not None:row[key]=value
        rows.append(row)
    with path.open('w', newline='') as out:
        writer=csv.DictWriter(out,fieldnames=fields,lineterminator="\n");writer.writeheader();writer.writerows(rows)
    print(f'Indexed {len(rows)} experiments; missing historical measurements remain empty')


if __name__=='__main__':main()
