import unittest
from pyannote.core import Annotation, Segment, Timeline
from pyannote.metrics.diarization import DiarizationErrorRate


class DiarizationScoring(unittest.TestCase):
    def test_permuted_ids_and_overlap_are_valid(self):
        reference, hypothesis = Annotation(), Annotation()
        reference[Segment(0, 2), 0] = 'A'
        reference[Segment(1, 3), 1] = 'B'
        hypothesis[Segment(0, 2), 0] = 'speaker_9'
        hypothesis[Segment(1, 3), 1] = 'speaker_2'
        metric = DiarizationErrorRate(collar=0.25, skip_overlap=False)
        self.assertEqual(metric(reference, hypothesis, uem=Timeline([Segment(0, 3)])), 0)

    def test_merging_distinct_speakers_is_penalized(self):
        reference, hypothesis = Annotation(), Annotation()
        reference[Segment(0, 1)] = 'A'
        reference[Segment(1, 2)] = 'B'
        hypothesis[Segment(0, 2)] = 'one_speaker'
        metric = DiarizationErrorRate(collar=0, skip_overlap=False)
        self.assertEqual(metric(reference, hypothesis, uem=Timeline([Segment(0, 2)])), 0.5)


if __name__ == '__main__':
    unittest.main()
