#!/usr/bin/env python3
"""Screen NeMo's auto speaker count/clustering on fresh ERes cluster vectors.

Cluster-level vectors isolate the previous global refinement decision. This is
not NeMo's multiscale segment pipeline. Its unconstrained grouping may merge
simultaneous predicted voices; conflicts are measured, never hidden/repaired.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from native_sdk import ROOT, NativeSdk, record_build
from probe_reclustering import Extractor, diarization
from probe_attribution import attribute
from run_file_pipeline import cpwer
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256

SOURCES = [
    ('eval/data/russian-conversation-pilot.jsonl','exp_0069'),
    ('eval/data/russian-conversation-heldout-session.jsonl','exp_0090'),
    ('eval/data/russian-conversation-movie-session.jsonl','exp_0096'),
    ('eval/data/russian-conversation-astrology-session.jsonl','exp_0155'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--experiment')
    args = parser.parse_args()
    if not args.experiment or not re.fullmatch(r'exp_[0-9]+',args.experiment): parser.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment; out.mkdir(parents=True,exist_ok=False)
    lock = json.loads((ROOT/'config/audio-models.lock.json').read_text())
    model = next(f for f in lock['files'] if f['path']=='models/diarization/embedding.onnx')
    ref = next(a for a in json.loads((ROOT/'config/audio-toolchain.lock.json').read_text())['research_artifacts'] if a['name']=='research/nmesc/offline_clustering.py')
    for path, digest in [(ROOT/model['path'],model['sha256']),(ROOT/'.tools'/ref['name'],ref['sha256'])]:
        if sha256(path)!=digest: raise ValueError('Changed model/reference')
    config = dict(vars(args),model_files=[model],source_artifact=ref, input_sha256={},
        sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),
        policy='same global cluster embeddings: three longest predicted spans >=800ms, centered <=8s, total2..20s. Native ERes; NeMo unmodified SpeakerClustering single scale defaults max8/oracle-1/enhanced40/rp.15/trials1. AHC complete-link .4 with predicted-overlap cannot-links. Missing embeddings remain distinct.',
        scope='six known silver records; reference clustering block on cluster-level inputs, not full NeMo multiscale pipeline; no GT count supplied')
    record_build(out,config)
    (out/'config.json').write_text(json.dumps(config,indent=2))
    sdk=NativeSdk(); extract=Extractor(sdk,ROOT/model['path']); cases=[]
    try:
        for manifest, baseline in SOURCES:
            config['input_sha256'][manifest]=sha256(ROOT/manifest)
            for entry in map(json.loads,(ROOT/manifest).read_text().splitlines()):
                ident=entry['audio_id']; path=ROOT/'.audio-runs'/baseline/ident/'transcript.json.trace.json'
                config['input_sha256'][str(path.relative_to(ROOT))]=sha256(path)
                trace=json.loads(path.read_text())
                for key in ['audio','reference']:
                    if sha256(ROOT/entry[key])!=entry[key+'_sha256']: raise ValueError('Changed fixture')
                pcm=sdk.decode(ROOT/entry['audio'],max_frames=180*16000+16)
                if len(pcm)>=180*16000+16: raise ValueError('Exceeds research180s')
                #155 is already refined: restore its saved initial predicted labels.
                original=trace.get('initial_speaker_turns',trace['speaker_turns'])
                labels=list(dict.fromkeys(t['speaker'] for t in original))
                if len(labels)>128: raise ValueError('Too many clusters')
                turns=[dict(start_ms=t['start_ms'],end_ms=t['end_ms'],speaker_id=str(t['speaker'])) for t in original]
                vectors={}; began=time.perf_counter()
                for label in labels:
                    spans=sorted([t for t in original if t['speaker']==label and t['end_ms']-t['start_ms']>=800],key=lambda t:t['end_ms']-t['start_ms'],reverse=True)[:3]
                    pieces=[]; remaining=320000
                    for t in spans:
                        width=min(8000,t['end_ms']-t['start_ms']); left=t['start_ms']+(t['end_ms']-t['start_ms']-width)//2
                        piece=pcm[int(left*16):int((left+width)*16)][:remaining];pieces.append(piece);remaining-=len(piece)
                    if pieces and sum(map(len,pieces))>=32000:
                        v=extract(np.concatenate(pieces))
                        if v is not None: vectors[label]=v
                embedding_seconds=time.perf_counter()-began
                valid=[label for label in labels if label in vectors]
                if not valid: raise ValueError('No usable embeddings')
                vector_path=out/(ident+'.vectors.npy');np.save(vector_path,np.stack([vectors[label] for label in valid]))
                completed=subprocess.run([str(ROOT/'.tools/frontend-env/bin/python'),str(ROOT/'eval/scripts/nmesc_worker.py'),str(vector_path)],capture_output=True,text=True,timeout=120,
                    env=dict(os.environ,OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1'))
                (out/(ident+'.worker.log')).write_text(completed.stdout+completed.stderr)
                if completed.returncode: raise RuntimeError('NeMo worker failed: '+completed.stderr[-2000:])
                result=json.loads(completed.stdout.strip().splitlines()[-1])
                if len(result['labels'])!=len(valid): raise ValueError('Clustering result length mismatch')
                n=len(labels); distance=np.full((n,n),2.); np.fill_diagonal(distance,0); forbidden=[]
                for i,a in enumerate(labels):
                    for j,b in enumerate(labels[:i]):
                        overlap=any(min(x['end_ms'],y['end_ms'])>max(x['start_ms'],y['start_ms']) for x in original if x['speaker']==a for y in original if y['speaker']==b)
                        if overlap: forbidden.append((a,b))
                        if not overlap and a in vectors and b in vectors: distance[i,j]=distance[j,i]=np.clip(1-np.dot(vectors[a],vectors[b]),0,2)
                ahc=fcluster(linkage(squareform(distance,checks=False),method='complete'),.4,criterion='distance') if n>1 else [1]
                mapping={label:'missing_'+str(label) for label in labels};mapping.update(dict(zip(valid,['nme_'+str(x) for x in result['labels']])))
                mappings=dict(original={label:str(label) for label in labels},ahc_04=dict(zip(labels,['ahc_'+str(g) for g in ahc])),nmesc=mapping)
                truth=json.loads((ROOT/entry['reference']).read_text())['transcript'];variants={}
                for name, groups in mappings.items():
                    changed=[dict(t,speaker_id=groups[original[i]['speaker']]) for i,t in enumerate(turns)]
                    assigned=attribute(trace['words'],changed)
                    if ' '.join(t['text'] for t in assigned)!=' '.join(w['text'] for w in trace['words']): raise ValueError('Words changed')
                    variants[name]=dict(speaker_attributed=cpwer(truth,assigned),predicted_speakers=len(set(groups.values())),
                        cannot_link_violations=sum(groups[a]==groups[b] for a,b in forbidden),**diarization(truth,changed,len(pcm)/16000))
                cases.append(dict(audio_id=ident,initial_clusters=len(labels),usable_embeddings=len(valid),embedding_seconds=embedding_seconds,
                    reference_worker=result,variants=variants))
                print(json.dumps(dict(audio_id=ident,scores={k:v['speaker_attributed']['cpwer'] for k,v in variants.items()})),flush=True)
    finally: extract.close()
    combined={}
    for name in cases[0]['variants']:
        values=[c['variants'][name] for c in cases]; errors=sum(v['speaker_attributed']['errors'] for v in values);total=sum(v['speaker_attributed']['reference_words'] for v in values)
        combined[name]=dict(errors=errors,reference_words=total,cpwer=errors/total,cannot_link_violations=sum(v['cannot_link_violations'] for v in values))
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],cases=cases,variants=combined)
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name,value in [('config.json',config),('metrics.json',metrics)]:
        (out/name).write_text(json.dumps(value,indent=2));(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(combined),flush=True)


if __name__=='__main__':main()
