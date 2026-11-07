"""Block A/B must not lose samples or feed a one-sample ASR tail."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_denoise_asr import chunk_ranges


class SourceChunks(unittest.TestCase):
    def test_all_source_samples_are_covered_once_at_model_boundaries(self):
        for frames in [0, 1, 15999, 16000, 320000, 320001, 335999, 336000, 2802748]:
            with self.subTest(frames=frames):
                offset = 0
                for start, size in chunk_ranges(frames):
                    self.assertEqual(start, offset)
                    self.assertGreater(size, 0)
                    self.assertLessEqual(size, 320000)
                    offset += size
                self.assertEqual(offset, frames)

    def test_long_recording_never_creates_subsecond_tail(self):
        for remainder in [1, 2, 15999, 16000, 16001]:
            ranges = list(chunk_ranges(320000+remainder))
            self.assertGreaterEqual(ranges[-1][1], 16000)


if __name__ == '__main__': unittest.main()
