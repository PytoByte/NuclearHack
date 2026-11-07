#!/usr/bin/env python3
"""Measure timeline delay against the source WAV, without inventing word alignments."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np
from scipy.signal import correlate,correlation_lags
from native_sdk import ROOT,NativeSdk,record_build
sys.path.insert(0,str(ROOT/'scripts'))
from bootstrap_models import sha256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',required=True);args=p.parse_args()
    out=ROOT/'.audio-runs'/args.experiment;out.mkdir(parents=True,exist_ok=False)
    config=dict(experiment_id=args.experiment,scope='Host codec timeline/signal comparison; not ASR/word timestamp accuracy',
        sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),correlation_window_seconds=10)
    record_build(out,config);(out/'config.json').write_text(json.dumps(config,indent=2))
    sdk=NativeSdk();cases=[]
    for name in ['dialogs-clean_2','dialogs-pauses_short_3','dialogs-noise_overlap_3']:
        wav=ROOT/'eval/data/audio'/(name+'.wav');mp3=wav.with_suffix('.mp3')
        a,b=sdk.decode(wav),sdk.decode(mp3);x,y=a[:160000],b[:160000]
        lag=int(correlation_lags(len(y),len(x))[np.argmax(correlate(y,x,method='fft'))])
        i,j=max(0,-lag),max(0,lag);n=min(len(a)-i,len(b)-j)
        clean=a[i:i+n].astype(np.float64);error=b[j:j+n].astype(np.float64)-clean
        mse=float(np.mean(error*error));snr=float(10*np.log10(np.mean(clean*clean)/mse)) if mse else None
        cases.append(dict(audio_id=name,wav_sha256=sha256(wav),mp3_sha256=sha256(mp3),source_frames=len(a),
            decoded_frames=len(b),extra_frames=len(b)-len(a),relative_signal_delay_ms=lag/16,
            signal_snr_after_delay_alignment_db=snr))
    metrics=dict(experiment_id=args.experiment,cases=cases,scope=config['scope'])
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2))
    (out/'environment.json').write_text(json.dumps(dict(host=platform.platform(),
        git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),indent=2))
    report=ROOT/'eval/results'/args.experiment;report.mkdir(parents=True,exist_ok=False)
    for name in ('config.json','metrics.json','environment.json'):(report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics,indent=2))


if __name__=='__main__':main()
