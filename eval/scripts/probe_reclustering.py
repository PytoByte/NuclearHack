#!/usr/bin/env python3
"""Research-only global speaker reclustering through the pinned native runtime.

Concatenates up to 20s from a cluster's three longest predicted speech spans.
Complete-link cosine clustering respects predicted simultaneous-speaker cannot-links.
No reference labels/counts/text enter embedding extraction or clustering.
"""
import argparse
import ctypes as C
import json
import re
import math
import os
import sys
import time
import numpy as np
from scipy.cluster.hierarchy import linkage,fcluster
from scipy.spatial.distance import squareform
from native_sdk import ROOT,NativeSdk,record_build
from probe_attribution import attribute
from run_file_pipeline import cpwer
from scoring import speaker_coverage,normalize
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256

class Config(C.Structure):
    _fields_=[('model',C.c_char_p),('num_threads',C.c_int32),('debug',C.c_int32),('provider',C.c_char_p)]

class Extractor:
    def __init__(self,sdk,model):
        self.lib=sdk.lib;l=self.lib
        l.SherpaOnnxCreateSpeakerEmbeddingExtractor.argtypes=[C.POINTER(Config)];l.SherpaOnnxCreateSpeakerEmbeddingExtractor.restype=C.c_void_p
        l.SherpaOnnxDestroySpeakerEmbeddingExtractor.argtypes=[C.c_void_p]
        l.SherpaOnnxSpeakerEmbeddingExtractorDim.argtypes=[C.c_void_p];l.SherpaOnnxSpeakerEmbeddingExtractorDim.restype=C.c_int32
        l.SherpaOnnxSpeakerEmbeddingExtractorCreateStream.argtypes=[C.c_void_p];l.SherpaOnnxSpeakerEmbeddingExtractorCreateStream.restype=C.c_void_p
        l.SherpaOnnxOnlineStreamAcceptWaveform.argtypes=[C.c_void_p,C.c_int32,C.POINTER(C.c_float),C.c_int32]
        l.SherpaOnnxOnlineStreamInputFinished.argtypes=[C.c_void_p]
        l.SherpaOnnxSpeakerEmbeddingExtractorIsReady.argtypes=[C.c_void_p,C.c_void_p];l.SherpaOnnxSpeakerEmbeddingExtractorIsReady.restype=C.c_int32
        l.SherpaOnnxSpeakerEmbeddingExtractorComputeEmbedding.argtypes=[C.c_void_p,C.c_void_p];l.SherpaOnnxSpeakerEmbeddingExtractorComputeEmbedding.restype=C.POINTER(C.c_float)
        l.SherpaOnnxSpeakerEmbeddingExtractorDestroyEmbedding.argtypes=[C.POINTER(C.c_float)]
        l.SherpaOnnxDestroyOnlineStream.argtypes=[C.c_void_p]
        self.handle=l.SherpaOnnxCreateSpeakerEmbeddingExtractor(C.byref(Config(os.fsencode(model),4,0,b'cpu')))
        if not self.handle:raise RuntimeError('Native extractor creation failed')
        self.dim=l.SherpaOnnxSpeakerEmbeddingExtractorDim(self.handle)
    def close(self):
        if self.handle:self.lib.SherpaOnnxDestroySpeakerEmbeddingExtractor(self.handle);self.handle=None
    def __call__(self,samples):
        l=self.lib;stream=l.SherpaOnnxSpeakerEmbeddingExtractorCreateStream(self.handle)
        if not stream:raise RuntimeError('Embedding stream unavailable')
        try:
            samples=np.ascontiguousarray(samples,dtype=np.float32)
            l.SherpaOnnxOnlineStreamAcceptWaveform(stream,16000,samples.ctypes.data_as(C.POINTER(C.c_float)),len(samples))
            l.SherpaOnnxOnlineStreamInputFinished(stream)
            if not l.SherpaOnnxSpeakerEmbeddingExtractorIsReady(self.handle,stream):return None
            value=l.SherpaOnnxSpeakerEmbeddingExtractorComputeEmbedding(self.handle,stream)
            if not value:raise RuntimeError('Null native embedding')
            try:vector=np.ctypeslib.as_array(value,shape=(self.dim,)).copy()
            finally:l.SherpaOnnxSpeakerEmbeddingExtractorDestroyEmbedding(value)
            norm=float(np.linalg.norm(vector))
            if not np.isfinite(vector).all() or norm<1e-8:return None
            return vector/norm
        finally:l.SherpaOnnxDestroyOnlineStream(stream)


def diarization(truth,turns,duration):
    from pyannote.core import Annotation,Segment,Timeline
    from pyannote.metrics.diarization import DiarizationErrorRate,JaccardErrorRate
    a,b=Annotation(),Annotation()
    for i,t in enumerate(truth):a[Segment(t['start_ms']/1000,t['end_ms']/1000),i]=t['speaker_id']
    for i,t in enumerate(turns):b[Segment(t['start_ms']/1000,t['end_ms']/1000),i]=t['speaker_id']
    uem=Timeline([Segment(0,duration)])
    d=DiarizationErrorRate(collar=.25,skip_overlap=False)(a,b,uem=uem,detailed=True)
    j=JaccardErrorRate(collar=.25,skip_overlap=False)(a,b,uem=uem)
    return dict(der_details={k:float(v) for k,v in d.items()},jer=float(j))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True)
    p.add_argument('--baseline',default='exp_0069');p.add_argument('--manifest',default='eval/data/russian-conversation-pilot.jsonl')
    p.add_argument('--embedding',default='embedding.onnx');p.add_argument('--thresholds',nargs='+',type=float,default=[.2,.3,.4]);args=p.parse_args()
    if any(not 0<t<2 for t in args.thresholds):p.error('Cosine distance threshold must be in (0,2)')
    if not re.fullmatch(r'exp_[0-9]+',args.experiment):p.error('Use exp_NNNN')
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    model_path='models/diarization/'+args.embedding;lock=json.loads((ROOT/'config/audio-models.lock.json').read_text())
    model=next(f for f in lock['files'] if f['path']==model_path)
    if sha256(ROOT/model_path)!=model['sha256']:raise ValueError('Embedding hash differs')
    config=dict(vars(args),thresholds=args.thresholds,min_turn_ms=800,max_span_ms=8000,max_spans=3,max_seconds=20,min_seconds=2,
        threads=4,method='complete-link cosine, simultaneous-speaker cannot-link',model_files=[model],
        manifest_sha256=sha256(ROOT/args.manifest),sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),
        input_sha256={},scope='research global reclustering; no oracle, whole-PCM research harness, not production integration')
    record_build(out,config);sdk=NativeSdk();start=time.perf_counter();extract=Extractor(sdk,ROOT/model_path);load=time.perf_counter()-start;cases=[]
    try:
        for f in map(json.loads,(ROOT/args.manifest).read_text().splitlines()):
            trace_path=ROOT/'.audio-runs'/args.baseline/f['audio_id']/'transcript.json.trace.json';config['input_sha256'][str(trace_path.relative_to(ROOT))]=sha256(trace_path)
            audio=ROOT/f['audio'];reference=ROOT/f['reference']
            if sha256(audio)!=f['audio_sha256'] or sha256(reference)!=f['reference_sha256']:raise ValueError('Changed corpus')
            trace=json.loads(trace_path.read_text());pcm=sdk.decode(audio,max_frames=math.ceil(f['audio_seconds']*16000)+16)
            ids={};turns=[]
            for t in trace['speaker_turns']:
                if t['speaker'] not in ids:ids[t['speaker']]='speaker_'+str(len(ids)+1)
                turns.append(dict(start_ms=t['start_ms'],end_ms=t['end_ms'],speaker_id=ids[t['speaker']]))
            labels=list(ids.values());vectors={};start=time.perf_counter()
            for speaker in labels:
                spans=sorted([t for t in turns if t['speaker_id']==speaker and t['end_ms']-t['start_ms']>=800],key=lambda t:t['end_ms']-t['start_ms'],reverse=True)[:3]
                pieces=[];remaining=20*16000
                for t in spans:
                    width=min(8000,t['end_ms']-t['start_ms']);left=t['start_ms']+(t['end_ms']-t['start_ms']-width)//2
                    piece=pcm[left*16:(left+width)*16][:remaining];pieces.append(piece);remaining-=len(piece)
                if pieces and sum(map(len,pieces))>=2*16000:vectors[speaker]=extract(np.concatenate(pieces))
            seconds=time.perf_counter()-start;n=len(labels);distance=np.full((n,n),2.0);np.fill_diagonal(distance,0);forbidden=[]
            for i,a in enumerate(labels):
                for j,b in enumerate(labels[:i]):
                    simultaneous=any(min(x['end_ms'],y['end_ms'])>max(x['start_ms'],y['start_ms']) for x in turns if x['speaker_id']==a for y in turns if y['speaker_id']==b)
                    if simultaneous:forbidden.append([a,b])
                    if not simultaneous and vectors.get(a) is not None and vectors.get(b) is not None:distance[i,j]=distance[j,i]=float(np.clip(1-np.dot(vectors[a],vectors[b]),0,2))
            tree=linkage(squareform(distance,checks=False),method='complete') if n>1 else None
            truth=json.loads(reference.read_text())['transcript'];predicted_base=attribute(trace['words'],turns)
            variants={'baseline':dict(speaker_attributed=cpwer(truth,predicted_base),**speaker_coverage(predicted_base),**diarization(truth,turns,f['audio_seconds']))};lexical=normalize(' '.join(w['text'] for w in trace['words']))
            for threshold in config['thresholds']:
                groups=fcluster(tree,t=threshold,criterion='distance') if tree is not None else [1]*n
                mapping=dict(zip(labels,['recluster_'+str(int(g)) for g in groups]));changed=[dict(t,speaker_id=mapping[t['speaker_id']]) for t in turns]
                predicted=attribute(trace['words'],changed)
                if normalize(' '.join(t['text'] for t in predicted))!=lexical:raise ValueError('Reclustering altered words')
                variants[str(threshold)]=dict(mapping=mapping,speaker_attributed=cpwer(truth,predicted),**speaker_coverage(predicted),**diarization(truth,changed,f['audio_seconds']))
            cases.append(dict(audio_id=f['audio_id'],embedding_seconds=seconds,embedding_clusters=sum(v is not None for v in vectors.values()),reference_speakers=len({t['speaker_id'] for t in truth}),cannot_links=forbidden,variants=variants))
            (out/(f['audio_id']+'.distances.json')).write_text(json.dumps(dict(labels=labels,distance=distance.tolist()),indent=2))
    finally:extract.close()
    aggregate={}
    for t in cases[0]['variants']:
        values=[c['variants'][t] for c in cases];errors=sum(v['speaker_attributed']['errors'] for v in values);words=sum(v['speaker_attributed']['reference_words'] for v in values)
        total=sum(v['der_details']['total'] for v in values);diar_errors=sum(sum(v['der_details'][k] for k in ['confusion','false alarm','missed detection']) for v in values)
        aggregate[t]=dict(cpwer=errors/words,der=diar_errors/total,jer=sum(c['variants'][t]['jer']*c['reference_speakers'] for c in cases)/sum(c['reference_speakers'] for c in cases))
    metrics=dict(experiment_id=args.experiment,scope=config['scope'],load_seconds=load,cases=cases,variants=aggregate)
    (out/'config.json').write_text(json.dumps(config,indent=2));(out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ['config.json','metrics.json']:(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(aggregate,indent=2))

if __name__=='__main__':main()
