#!/usr/bin/env python3
"""Real new file C ABI cancellation, resume, busy and asset protection checks."""
import argparse
import ctypes as C
import hashlib
import json
import os
import re
import sys
from native_sdk import ROOT, NativeSdk, record_build
from probe_checkpoint import Pipeline, Options, PROGRESS
from probe_native_streaming import Config as Speaker
sys.path.insert(0, str(ROOT/'scripts'))
from bootstrap_models import sha256
from audio_tools import transcript as validate


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--experiment', required=True); args = p.parse_args()
    if not re.fullmatch(r'exp_[0-9]+', args.experiment): p.error('Use exp_NNNN')
    out = ROOT/'.audio-runs'/args.experiment; out.mkdir(parents=True, exist_ok=False)
    diagnostics = (out/'stderr.log').open('w'); os.dup2(diagnostics.fileno(), 2)
    audio = ROOT/'eval/data/audio/dialogs-clean_2.mp3'
    spk_path = ROOT/'models/nemotron3-diarization/model_quantized.onnx'
    lock = json.loads((ROOT/'config/audio-models.lock.json').read_text())
    paths = ['models/giga-v3-ctc/model.int8.onnx', 'models/giga-v3-ctc/tokens.txt',
             'models/nemotron3-diarization/model_quantized.onnx', 'models/nemotron3-diarization/model_quantized.onnx_data',
             'models/diarization/segmentation-model.onnx', 'models/diarization/embedding.onnx']
    files = [next(f for f in lock['files'] if f['path'] == path) for path in paths]
    for f in files:
        if sha256(ROOT/f['path']) != f['sha256']: raise ValueError('Changed model asset')
    config = dict(vars(args), sdk_sha256=sha256(ROOT/'.build/audio/libnuclear_audio.so'), model_files=files,
        audio_sha256=sha256(audio), scope='host real-model new file API controls; no quality or target timing claims')
    record_build(out, config); (out/'config.json').write_text(json.dumps(config, indent=2))
    sdk = NativeSdk(); lib = sdk.lib
    function = lib.nh_transcribe_file_with_streaming_diarizer
    function.argtypes = [C.c_char_p, C.POINTER(Pipeline), C.POINTER(Options), C.POINTER(Speaker), PROGRESS, C.c_void_p]
    lib.nh_transcribe_file_with_options.argtypes = [C.c_char_p, C.POINTER(Pipeline), C.POINTER(Options), PROGRESS, C.c_void_p]
    cache = out/'cache'; cache.mkdir(); cases = []; exported = {}
    sentinel = b'{"transcript":[]}\n'; trace_sentinel = b'{"sentinel":true}\n'
    def run(name, expected, cancel_stage=None, cancel_positive=False, nested=False, limit=0, legacy=False, alias=False):
        folder = out/name; folder.mkdir()
        output = folder/'transcript.json'; trace = folder/'trace.json'
        output.write_bytes(sentinel); trace.write_bytes(trace_sentinel)
        output_arg = ROOT/paths[3] if alias else output
        cfg = Pipeline(C.sizeof(Pipeline), os.fsencode(ROOT/paths[0]), os.fsencode(ROOT/paths[1]),
            os.fsencode(ROOT/paths[4]) if legacy else None, os.fsencode(ROOT/paths[5]) if legacy else None,
            os.fsencode(folder), os.fsencode(output_arg), os.fsencode(trace), 4, 20, 600, .8 if legacy else 0)
        options = Options(C.sizeof(Options), .3 if legacy else 0, .5 if legacy else 0, 0, os.fsencode(cache), .1 if legacy else 0)
        speaker = Speaker(C.sizeof(Speaker), os.fsencode(spk_path), 4, 1, limit)
        stages = []; nested_codes = []
        @PROGRESS
        def progress(stage, done, total, user):
            stage = stage.decode(); stages.append(dict(stage=stage, done=done, total=total))
            if nested and stage == 'speaker_stream_load':
                nested_codes.append(function(os.fsencode(audio), C.byref(cfg), C.byref(options), C.byref(speaker), progress, None))
                return 1
            return int(stage == cancel_stage and (not cancel_positive or done > 0))
        before_weights = sha256(ROOT/paths[3]) if alias else None
        status = (lib.nh_transcribe_file_with_options(os.fsencode(audio), C.byref(cfg), C.byref(options), progress, None)
                  if legacy else function(os.fsencode(audio), C.byref(cfg), C.byref(options), C.byref(speaker), progress, None))
        error = lib.nh_last_error().decode() if status else ''
        if status != expected: raise AssertionError((name, status, error))
        if status:
            if output.read_bytes() != sentinel or trace.read_bytes() != trace_sentinel:
                raise AssertionError('Failed/cancelled operation replaced an existing export')
        else:
            validate(json.loads(output.read_text())); exported[name] = json.loads(trace.read_text())
        if nested and nested_codes != [5]: raise AssertionError('Nested new API was not busy')
        if alias and sha256(ROOT/paths[3]) != before_weights: raise AssertionError('Protected external weights changed')
        completed = [s['done'] for s in stages if s['stage'] == 'speaker_stream']
        if completed != sorted(completed): raise AssertionError('Speaker progress moves backwards')
        case = dict(case=name, status=status, asr_loads=sum(s['stage']=='asr_load' for s in stages),
            cached_chunks=sum(s['stage']=='asr_cached' for s in stages), nested_status=nested_codes,
            export_preserved_on_failure=bool(status), error=error, speaker_progress_monotonic=True)
        if limit and any(s['stage'].startswith('asr') or s['stage']=='speaker_stream_load' for s in stages):
            raise AssertionError('Duration limit did not reject before loading models')
        if name in ['reentry', 'cancel_after_inference', 'resume', 'legacy_cache_reuse'] and case['asr_loads']:
            raise AssertionError('Shared ASR checkpoint was not reused')
        (folder/'events.json').write_text(json.dumps(stages, indent=2)); cases.append(case)
    run('seed_cancel_before_speaker', 4, cancel_stage='speaker_stream_load')
    run('reentry', 4, nested=True)
    run('cancel_after_inference', 4, cancel_stage='speaker_stream', cancel_positive=True)
    run('resume', 0)
    run('legacy_cache_reuse', 0, legacy=True)
    run('duration_budget', 1, limit=1)
    run('protect_external_weights', 1, alias=True)
    resumed, legacy = exported['resume'], exported['legacy_cache_reuse']
    if resumed['words'] != legacy['words'] or resumed['asr'] != legacy['asr']:
        raise AssertionError('Backend switch changed cached ASR text/times')
    pcm = sdk.decode(audio)
    if resumed['decoded_pcm_sha256'] != hashlib.sha256(pcm.tobytes()).hexdigest():
        raise AssertionError('Source PCM identity differs')
    metrics = dict(experiment_id=args.experiment, scope=config['scope'], cases=cases, passed=True,
                   shared_asr_checkpoint_exact=True, decoded_pcm_sha_exact=True)
    report = ROOT/'eval/results'/args.experiment; report.mkdir(parents=True, exist_ok=False)
    (out/'metrics.json').write_text(json.dumps(metrics, indent=2))
    for name in ['config.json', 'metrics.json']: (report/name).write_bytes((out/name).read_bytes())
    print(json.dumps(metrics, indent=2))


if __name__ == '__main__': main()
