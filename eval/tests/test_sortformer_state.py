"""Model-free checks for streaming context boundaries and bounded cache lifecycle."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_sortformer as candidate


class FakeSession:
    def __init__(self):
        self.inputs = []

    def run(self, _, inputs):
        self.inputs.append({k: v.copy() for k, v in inputs.items()})
        count = (len(inputs['chunk'][0])+7)//8
        cache, fifo = len(inputs['spkcache'][0]), len(inputs['fifo'][0])
        probs = np.zeros((1, cache+fifo+count, 4), np.float32)
        probs[0, :, 0] = .9
        # Each local frame has an identifiable embedding, including discarded LC/RC.
        embeddings = np.repeat(np.arange(count, dtype=np.float32)[None, :, None], 512, axis=2)
        return probs, embeddings, np.array([count], np.int64)


def runtime():
    obj = candidate.Sortformer.__new__(candidate.Sortformer)
    obj.session = FakeSession()
    obj.chunk, obj.right, obj.fifo_cap, obj.update = candidate.PROFILES['low']
    obj.reset()
    return obj


class StreamingState(unittest.TestCase):
    def test_left_and_right_context_are_not_committed(self):
        obj = runtime()
        obj.step(np.zeros((112, 128), np.float32), left=1, keep=6)
        np.testing.assert_array_equal(obj.fifo[:, 0], [1, 2, 3, 4, 5, 6])
        self.assertEqual(obj.steps[0]['emitted_frames'], 6)

    def test_cache_compression_and_reset(self):
        obj = runtime()
        for i in range(100):
            obj.step(np.zeros((112, 128), np.float32), left=1, keep=6)
            self.assertLessEqual(len(obj.cache), 188)
            self.assertLessEqual(len(obj.fifo), 188)
        self.assertTrue(obj.compressed)
        self.assertEqual(obj.cache_probs.shape, (188, 4))
        self.assertTrue(np.isfinite(obj.cache).all())
        obj.reset()
        self.assertEqual(len(obj.cache), 0)
        self.assertEqual(len(obj.fifo), 0)
        self.assertEqual(obj.steps, [])

    def test_arrived_window_never_reads_beyond_explicit_right_context(self):
        obj = runtime()
        pcm = np.arange(3*16000, dtype=np.float32)
        slices = []

        def frontend(samples):
            slices.append((int(samples[0]), int(samples[-1])+1))
            return np.zeros((len(samples)//160, 128), np.float32)

        with patch.object(candidate, 'mel_features', frontend):
            predictions = obj.predict(pcm, 'window')
        self.assertEqual(slices[0], (0, 104*160))
        self.assertEqual(slices[1], (40*160, 152*160))
        self.assertEqual(slices[-1][1], len(pcm))
        self.assertEqual(len(predictions), (len(pcm)//160+7)//8)
        self.assertLessEqual(max(b-a for a, b in slices), 112*160)

    def test_silence_and_subframe_frontend_remain_finite(self):
        for frames in [0, 1, 159, 160, 16000]:
            features = candidate.mel_features(np.zeros(frames, np.float32))
            self.assertEqual(features.shape, (frames//160, 128))
            self.assertEqual(features.dtype, np.float32)
            self.assertTrue(np.isfinite(features).all())


if __name__ == '__main__':
    unittest.main()
