"""Validate Viterbi against exhaustive paths, rather than mirroring the DP."""
import itertools
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from ctc_alignment import align_tokens


class CtcAlignmentTest(unittest.TestCase):
    def test_exhaustive_reference(self):
        rng = np.random.default_rng(42)
        for target in [[1], [1, 1], [1, 2], [2, 1, 2]]:
            scores = rng.normal(size=(5, 3))
            valid = []
            for path in itertools.product(range(3), repeat=5):
                collapsed = [v for i,v in enumerate(path) if v and (i == 0 or path[i-1] != v)]
                if collapsed == target:
                    valid.append(sum(scores[i,v] for i,v in enumerate(path)))
            spans, score = align_tokens(scores, target)
            self.assertAlmostEqual(score, max(valid))
            self.assertEqual(len(spans), len(target))
            self.assertTrue(all(a < b for a,b in spans))
            self.assertTrue(all(spans[i][1] <= spans[i+1][0] for i in range(len(spans)-1)))

    def test_repeated_label_needs_blank(self):
        with self.assertRaises(ValueError):
            align_tokens(np.zeros((2, 3)), [1, 1])
        self.assertEqual(align_tokens(np.zeros((3, 3)), [1, 1])[0], [(0,1), (2,3)])

    def test_invalid(self):
        for scores, target in [(np.array([[np.nan, 0]]), [1]), (np.zeros((3,2)), [0]), (np.zeros((3,2)), [2]), (np.zeros((3,2)), [])]:
            with self.assertRaises(ValueError):
                align_tokens(scores, target)
