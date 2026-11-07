import ctypes as C
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_sdk import NativeSdk, ROOT, VadConfig, SPEECH

@unittest.skipUnless((ROOT/'models/silero-vad/silero.onnx').exists(),'Pinned Silero weights required')
class NativeVad(unittest.TestCase):
    def test_silence_flush_and_streaming_block_invariance(self):
        sdk=NativeSdk()
        if not hasattr(sdk.lib,'nh_vad_create'):self.skipTest('Rebuild native SDK with VAD')
        sdk.speech_regions(np.zeros(16000,dtype=np.float32)) # config + native function signatures
        def detect(samples,block):
            lib=sdk.lib;handle=C.c_void_p();turns=[]
            options=VadConfig(C.sizeof(VadConfig),str(ROOT/'models/silero-vad/silero.onnx').encode(),1,.5,.3,.1,20)
            @SPEECH
            def consume(start,end,user):turns.append((int(start),int(end)));return 0
            sdk.check(lib.nh_vad_create(C.byref(options),C.byref(handle)))
            try:
                for i in range(0,len(samples),block):
                    chunk=np.ascontiguousarray(samples[i:i+block]);sdk.check(lib.nh_vad_accept(handle,chunk.ctypes.data_as(C.POINTER(C.c_float)),len(chunk),consume,None))
                sdk.check(lib.nh_vad_flush(handle,consume,None));sdk.check(lib.nh_vad_flush(handle,consume,None))
                # Flush cannot duplicate results and a completed stream cannot accept new input.
                self.assertEqual(lib.nh_vad_accept(handle,samples.ctypes.data_as(C.POINTER(C.c_float)),1,consume,None),1)
            finally:lib.nh_vad_destroy(handle)
            return turns
        silence=np.zeros(32000,dtype=np.float32)
        self.assertEqual(detect(silence,512),[])
        fixture=ROOT/'eval/data/audio/dialogs-clean_2.mp3'
        if fixture.exists():
            samples=sdk.decode(fixture)
            a,b=detect(samples,512),detect(samples,16000)
            self.assertTrue(a);self.assertEqual(a,b)
            self.assertTrue(all(0<=start<end<=len(samples) for start,end in a))
