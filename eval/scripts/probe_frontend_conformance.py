#!/usr/bin/env python3
"""Compare research NumPy features with an independent Torch/librosa reference.

Reference equations: NVIDIA NeMo FilterbankFeatures and Transformers
NemotronAsrStreamingFeatureExtractor. This is frontend conformance only,
not full model/state or NeMo pipeline numerical parity.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def reference(source, target):
    import importlib.metadata
    import librosa
    import numpy as np
    import torch
    torch.set_num_threads(4)
    outputs = {}
    filters = torch.from_numpy(librosa.filters.mel(sr=16000, n_fft=512, n_mels=128, fmin=0., fmax=8000., norm='slaney'))
    window = torch.hann_window(400, periodic=False)
    with np.load(source) as cases:
        for name in cases.files:
            pcm = torch.from_numpy(cases[name].copy())[None]
            emphasized = torch.cat([pcm[:, :1], pcm[:, 1:]-.97*pcm[:, :-1]], dim=1)
            spectrum = torch.stft(emphasized, n_fft=512, hop_length=160, win_length=400,
                                  window=window, center=True, pad_mode='constant', return_complex=True)
            power = spectrum.abs()**2
            values = torch.log(filters @ power + 2**-24).transpose(1, 2)
            outputs[name] = values[0, :len(cases[name])//160].numpy()
    np.savez(target, **outputs)
    versions = {name: importlib.metadata.version(name) for name in ['torch', 'librosa', 'numpy', 'scipy']}
    Path(str(target)+'.versions.json').write_text(json.dumps(versions, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', nargs=2, metavar=('INPUT_NPZ', 'OUTPUT_NPZ'))
    p.add_argument('--experiment')
    p.add_argument('--reference-python', default='.tools/frontend-env/bin/python')
    args = p.parse_args()
    if args.reference:
        reference(*args.reference)
        return
    if not args.experiment or not re.fullmatch(r'exp_[0-9]+', args.experiment):
        p.error('Use --experiment exp_NNNN')
    import numpy as np
    from native_sdk import ROOT, NativeSdk, record_build
    from probe_sortformer import mel_features
    sys.path.insert(0, str(ROOT/'scripts'))
    from bootstrap_models import sha256
    out = ROOT/'.audio-runs'/args.experiment
    out.mkdir(parents=True, exist_ok=False)
    audio = ROOT/'eval/data/audio/ru-youtube-astrology.wav'
    config = dict(vars(args), audio_sha256=sha256(audio), sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'),
                  max_absolute_tolerance=5e-5, mean_absolute_tolerance=5e-6,
                  reference_recipe='symmetric Torch Hann400, FFT512/hop160 center/constant, librosa128Slaney, preemphasis.97, dither0, logguard2^-24, floorvalidlength',
                  source_url='https://github.com/huggingface/transformers/blob/0f53828e83f2212060233d2ea552cc76617b8712/src/transformers/models/nemotron_asr_streaming/feature_extraction_nemotron_asr_streaming.py',
                  scope='independent frontend numeric conformance; not full NeMo/state parity or timestamp accuracy')
    record_build(out, config)
    (out/'config.json').write_text(json.dumps(config, indent=2))
    pcm = NativeSdk().decode(audio, max_frames=180*16000+16)
    impulse = np.zeros(16001, np.float32)
    impulse[[0, 100, 7999, 16000]] = [.5, -.5, 1, .2]
    inputs = dict(silence=np.zeros(64000, np.float32), impulse=impulse,
                  sine=(.2*np.sin(2*np.pi*997*np.arange(4000)/16000)).astype(np.float32),
                  real=pcm[:64000].copy())
    np.savez(out/'inputs.npz', **inputs)
    subprocess.run([str(ROOT/args.reference_python), str(Path(__file__).resolve()), '--reference',
                    str(out/'inputs.npz'), str(out/'reference.npz')], check=True)
    versions = json.loads((out/'reference.npz.versions.json').read_text())
    cases = []
    with np.load(out/'reference.npz') as expected:
        for name, samples in inputs.items():
            actual = mel_features(samples)
            if actual.shape != expected[name].shape or not np.isfinite(actual).all():
                raise ValueError('Invalid frontend shape/value')
            difference = abs(actual-expected[name])
            maximum, mean = float(difference.max(initial=0)), float(difference.mean())
            cases.append(dict(case=name, frames=len(actual), max_absolute_difference=maximum, mean_absolute_difference=mean,
                              passed=maximum<=5e-5 and mean<=5e-6))
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], reference_versions=versions,
                   cases=cases, all_passed=all(c['passed'] for c in cases))
    report = ROOT/'eval/results'/args.experiment
    report.mkdir(parents=True, exist_ok=False)
    for name, obj in [('config.json', config), ('metrics.json', metrics)]:
        (out/name).write_text(json.dumps(obj, indent=2))
        (report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics, indent=2))
    if not metrics['all_passed']:
        raise ValueError('Frontend exceeds predeclared reference tolerances')


if __name__ == '__main__':
    main()
