"""Tests exercise the public shared-library ABI; no model/dummy transcript."""
import ctypes as C
from concurrent.futures import ThreadPoolExecutor
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / '.build/audio/libnuclear_audio.so'
CALLBACK = C.CFUNCTYPE(C.c_int32, C.POINTER(C.c_float), C.c_uint32, C.c_uint64, C.c_void_p)


@unittest.skipUnless(LIB.exists(), 'Build native SDK with make native-test')
class NativeAudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = C.CDLL(str(LIB))
        cls.lib.nh_decode_file.argtypes = [C.c_char_p, C.c_uint32, C.c_uint32, CALLBACK, C.c_void_p]
        cls.lib.nh_decode_file.restype = C.c_int
        cls.lib.nh_last_error.restype = C.c_char_p

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'signal.wav'

    def signal(self, rate=48000, frequency=1000, seconds=1, channels=1):
        with wave.open(str(self.path), 'wb') as target:
            target.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
            values = [int(16000 * math.sin(2 * math.pi * frequency * i / rate)) for i in range(int(rate * seconds))]
            target.writeframes(b''.join(struct.pack('<h', value) * channels for value in values))

    def decode(self, path=None, block=1024, cancel=False):
        samples, offsets, sizes = [], [], []
        @CALLBACK
        def consume(pcm, frames, offset, user):
            samples.extend(pcm[:frames])
            offsets.append(offset)
            sizes.append(frames)
            return int(cancel)
        status = self.lib.nh_decode_file(os.fsencode(path or self.path), 16000, block, consume, None)
        return status, samples, offsets, sizes

    def test_resampling_offsets_and_signal(self):
        self.signal()
        status, samples, offsets, sizes = self.decode()
        self.assertEqual(status, 0)
        self.assertLessEqual(abs(len(samples) - 16000), 2)
        self.assertLessEqual(max(sizes), 1024)
        self.assertEqual(offsets, [sum(sizes[:i]) for i in range(len(sizes))])
        rms = math.sqrt(sum(x*x for x in samples[100:]) / len(samples[100:]))
        self.assertGreater(rms, 0.30)
        self.assertLess(rms, 0.37)

    def test_downsampling_suppresses_alias(self):
        self.signal(frequency=12000)
        status, samples, _, _ = self.decode()
        self.assertEqual(status, 0)
        rms = math.sqrt(sum(x*x for x in samples[100:]) / len(samples[100:]))
        self.assertLess(rms, 0.04)

    def test_cancellation_is_bounded(self):
        self.signal(seconds=2)
        status, _, offsets, _ = self.decode(cancel=True)
        self.assertEqual(status, 4)
        self.assertEqual(offsets, [0])

    def test_concurrent_decoders_have_independent_state(self):
        self.signal(rate=16000)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.decode(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 0)

    def test_corrupt_input_has_error(self):
        self.path.write_bytes(b'corrupt audio')
        self.assertEqual(self.decode()[0], 2)
        self.assertTrue(self.lib.nh_last_error())

    def test_mp3_stereo(self):
        self.signal(channels=2)
        executable = shutil.which('ffmpeg') or str(ROOT / '.tools/bin/ffmpeg')
        mp3 = self.path.with_suffix('.mp3')
        subprocess.run([executable, '-v', 'error', '-y', '-i', str(self.path), str(mp3)], check=True)
        status, samples, _, _ = self.decode(mp3)
        self.assertEqual(status, 0)
        # Container encoder padding differs across decoders; do not imply alignment parity.
        self.assertGreaterEqual(len(samples), 16000)
        self.assertLess(len(samples), 18000)


if __name__ == '__main__':
    unittest.main()
