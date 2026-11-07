"""Research harness calls the production C ABI, with no Python ASR backend."""
import ctypes as C
import json
import os
import hashlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]

def record_harness(directory,config):
    snapshot=directory/'harness';snapshot.mkdir(exist_ok=True)
    config['harness_files']={}
    for source in sorted((ROOT/'eval/scripts').glob('*.py')):
        data=source.read_bytes();(snapshot/source.name).write_bytes(data)
        config['harness_files'][source.name]=hashlib.sha256(data).hexdigest()

def record_build(directory,config):
    """Capture the actual scorer/harness and post-build source/binary provenance."""
    record_harness(directory,config)
    provenance=ROOT/'.build/audio/build-provenance.json'
    if provenance.exists():
        info=json.loads(provenance.read_text())
        if config.get('sdk_sha256')!=info['sdk_sha256']:raise ValueError('Build provenance is stale; rebuild SDK')
        data=provenance.read_bytes();(directory/'build-provenance.json').write_bytes(data)
        config['build_provenance_sha256']=hashlib.sha256(data).hexdigest()
        config['source_snapshot']=info['source_snapshot']
    else:config['build_provenance']='not captured in this historical build'

PCM = C.CFUNCTYPE(C.c_int32, C.POINTER(C.c_float), C.c_uint32, C.c_uint64, C.c_void_p)
ASR = C.CFUNCTYPE(C.c_int32, C.c_char_p, C.c_char_p, C.c_void_p)
TURN = C.CFUNCTYPE(C.c_int32, C.c_int32, C.c_double, C.c_double, C.c_void_p)
SPEECH = C.CFUNCTYPE(C.c_int32,C.c_uint64,C.c_uint64,C.c_void_p)

class VadConfig(C.Structure):
    _fields_=[('struct_size',C.c_uint32),('model',C.c_char_p),('threads',C.c_uint32),
        ('threshold',C.c_float),('min_silence_seconds',C.c_float),('min_speech_seconds',C.c_float),('max_speech_seconds',C.c_float)]

class AsrConfig(C.Structure):
    _fields_ = [('struct_size', C.c_uint32)] + [(k,C.c_char_p) for k in
        ('family','model','decoder','joiner','tokens','language','decoding_method','hotwords_file')] + [
        ('threads',C.c_uint32),('max_active_paths',C.c_uint32),('hotwords_score',C.c_float)]

class DiarConfig(C.Structure):
    _fields_ = [('struct_size',C.c_uint32),('segmentation',C.c_char_p),('embedding',C.c_char_p),
        ('threads',C.c_uint32),('cluster_threshold',C.c_float),('min_duration_on',C.c_float),
        ('min_duration_off',C.c_float),('oracle_speakers',C.c_int32)]


class NativeSdk:
    def __init__(self):
        self.lib = C.CDLL(str(ROOT / '.build/audio/libnuclear_audio.so'))
        lib = self.lib
        lib.nh_last_error.restype = C.c_char_p
        lib.nh_sherpa_version.restype = C.c_char_p
        lib.nh_decode_file.argtypes = [C.c_char_p, C.c_uint32, C.c_uint32, PCM, C.c_void_p]
        lib.nh_asr_create_ctc.argtypes = [C.c_char_p, C.c_char_p, C.c_uint32, C.POINTER(C.c_void_p)]
        lib.nh_asr_decode.argtypes = [C.c_void_p, C.POINTER(C.c_float), C.c_uint32, ASR, C.c_void_p]
        lib.nh_asr_destroy.argtypes = [C.c_void_p]
        if hasattr(lib, 'nh_asr_create_transducer'):
            lib.nh_asr_create_transducer.argtypes = [C.c_char_p] * 4 + [C.c_uint32, C.POINTER(C.c_void_p)]
        if hasattr(lib, 'nh_asr_create_whisper'):
            lib.nh_asr_create_whisper.argtypes = [C.c_char_p] * 3 + [C.c_uint32, C.POINTER(C.c_void_p)]

    def check(self, code):
        if code:
            raise RuntimeError(f'native status {code}: {self.lib.nh_last_error().decode()}')

    def decode(self, path, max_frames=None):
        chunks, errors = [], []
        @PCM
        def consume(samples, frames, start, user):
            try:
                count = min(frames, max_frames - start) if max_frames is not None else frames
                if count > 0:
                    chunks.append(np.ctypeslib.as_array(samples, shape=(count,)).copy())
                return int(max_frames is not None and start + frames >= max_frames)
            except Exception as error:
                errors.append(error)
                return 1
        code = self.lib.nh_decode_file(os.fsencode(path), 16000, 16000, consume, None)
        if code != 4 or max_frames is None or errors:
            self.check(code)
        if errors:
            raise errors[0]
        return np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)

    def create(self, family, files, threads, method='greedy_search', language='ru', hotwords=None):
        handle = C.c_void_p()
        files = {Path(p).name: os.fsencode(ROOT / p) for p in files}
        if hasattr(self.lib, 'nh_asr_create'):
            self.lib.nh_asr_create.argtypes = [C.POINTER(AsrConfig), C.POINTER(C.c_void_p)]
            model,decoder,joiner,tokens = (
                (files.get('model.int8.onnx',files.get('model.onnx')),None,None,files.get('tokens.txt')) if family=='ctc' else
                (files.get('encoder.int8.onnx'),files.get('decoder.onnx'),files.get('joiner.onnx'),files.get('tokens.txt')) if family=='transducer' else
                (files.get('base-encoder.int8.onnx'),files.get('base-decoder.int8.onnx'),None,files.get('base-tokens.txt')))
            config=AsrConfig(C.sizeof(AsrConfig),family.encode(),model,decoder,joiner,tokens,language.encode(),
                method.encode(),os.fsencode(hotwords) if hotwords else None,threads,4,1.5)
            self.check(self.lib.nh_asr_create(C.byref(config),C.byref(handle)))
            return handle
        if family == 'ctc':
            code = self.lib.nh_asr_create_ctc(files['model.int8.onnx'], files['tokens.txt'], threads, C.byref(handle))
        elif family == 'transducer':
            code = self.lib.nh_asr_create_transducer(files['encoder.int8.onnx'], files['decoder.onnx'],
                files['joiner.onnx'], files['tokens.txt'], threads, C.byref(handle))
        elif family == 'whisper':
            code = self.lib.nh_asr_create_whisper(files['base-encoder.int8.onnx'], files['base-decoder.int8.onnx'],
                files['base-tokens.txt'], threads, C.byref(handle))
        else:
            raise ValueError(f'Unknown model family: {family}')
        self.check(code)
        return handle

    def transcribe(self, handle, samples):
        result, errors = [], []
        @ASR
        def consume(text, backend_json, user):
            try:
                result.append(dict(text=text.decode('utf-8'), backend=json.loads(backend_json.decode('utf-8'))))
                return 0
            except Exception as error:
                errors.append(error)
                return 1
        samples = np.ascontiguousarray(samples, dtype=np.float32)
        self.check(self.lib.nh_asr_decode(handle, samples.ctypes.data_as(C.POINTER(C.c_float)), len(samples), consume, None))
        if errors:
            raise errors[0]
        if len(result) != 1:
            raise RuntimeError('Expected exactly one ASR result')
        return result[0]

    def speech_regions(self,samples,threshold=0.5,padding_ms=250,min_speech=0.1,min_silence=0.3):
        lib=self.lib;handle=C.c_void_p();regions=[]
        lib.nh_vad_create.argtypes=[C.POINTER(VadConfig),C.POINTER(C.c_void_p)]
        lib.nh_vad_accept.argtypes=[C.c_void_p,C.POINTER(C.c_float),C.c_uint32,SPEECH,C.c_void_p]
        lib.nh_vad_flush.argtypes=[C.c_void_p,SPEECH,C.c_void_p];lib.nh_vad_destroy.argtypes=[C.c_void_p]
        options=VadConfig(C.sizeof(VadConfig),os.fsencode(ROOT/'models/silero-vad/silero.onnx'),1,
            threshold,min_silence,min_speech,20)
        @SPEECH
        def consume(start,end,user):regions.append((int(start),int(end)));return 0
        self.check(lib.nh_vad_create(C.byref(options),C.byref(handle)))
        try:
            for offset in range(0,len(samples),16000):
                chunk=np.ascontiguousarray(samples[offset:offset+16000],dtype=np.float32)
                self.check(lib.nh_vad_accept(handle,chunk.ctypes.data_as(C.POINTER(C.c_float)),len(chunk),consume,None))
            self.check(lib.nh_vad_flush(handle,consume,None))
        finally:lib.nh_vad_destroy(handle)
        padded=[];pad=padding_ms*16
        for start,end in regions:
            start=max(0,start-pad);end=min(len(samples),end+pad)
            if padded and start<=padded[-1][1]:padded[-1]=(padded[-1][0],max(end,padded[-1][1]))
            else:padded.append((start,end))
        return padded,regions
