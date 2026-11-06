import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from scoring import aggregate, counts, normalize


class Scoring(unittest.TestCase):
    def test_normalization_preserves_fillers_and_numbers(self):
        self.assertEqual(normalize('Ээ, ещё 42 — да-да!'), 'ээ еще 42 да да')
        self.assertNotEqual(normalize('42'), normalize('сорок два'))

    def test_wer_uses_corpus_word_counts(self):
        total = aggregate([counts('а б в г', 'а б в г'), counts('да', 'нет')])
        self.assertEqual(total['wer'], 0.2)

    def test_insertions_and_deletions_are_counted(self):
        self.assertEqual(counts('да', 'да да')['insertions'], 1)
        self.assertEqual(counts('да да', 'да')['deletions'], 1)

    def test_raw_and_normalized_are_separate(self):
        self.assertEqual(aggregate([counts('Ещё, да!', 'еще да')])['wer'], 0)
        self.assertGreater(aggregate([counts('Ещё, да!', 'еще да', False)])['wer'], 0)


if __name__ == '__main__':
    unittest.main()
