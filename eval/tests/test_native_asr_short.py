import json
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_sdk import NativeSdk,ROOT

@unittest.skipUnless((ROOT/'models/giga-v3-ctc/model.int8.onnx').exists(),'Pinned real ASR weights required')
class ShortAsr(unittest.TestCase):
    def test_sub_frame_input_cannot_crash_conformer(self):
        sdk=NativeSdk();catalog=json.loads((ROOT/'config/audio-models.lock.json').read_text())
        model=next(m for m in catalog['models'] if m['id']=='giga-v3-ctc')
        handle=sdk.create('ctc',model['files'],1)
        try:
            for frames in [1,160,8000]:
                result=sdk.transcribe(handle,np.zeros(frames,dtype=np.float32))
                self.assertIsInstance(result['text'],str)
                self.assertIsInstance(result['backend']['tokens'],list)
        finally:sdk.lib.nh_asr_destroy(handle)
