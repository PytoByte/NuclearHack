import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from scoring import aggregate, counts, normalize, punctuation_counts, text_metrics, speaker_coverage


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

    def test_punctuation_anchors_survive_insertions(self):
        result=punctuation_counts('да, конечно.', 'ну да, конечно.')
        self.assertEqual(result['end_to_end'],dict(true_positive=2,false_positive=0,false_negative=0))
        result=punctuation_counts('да, конечно.', 'нет, конечно.')
        self.assertEqual(result['end_to_end'],dict(true_positive=1,false_positive=1,false_negative=1))

    def test_punctuation_token_wer_and_lexical_wer_are_distinct(self):
        result=text_metrics('Да, ещё!', 'да еще')
        self.assertEqual(aggregate([result['normalized']])['wer'],0)
        self.assertEqual(aggregate([result['punctuation_token_wer']])['wer'],0.5)
        self.assertEqual(result['punctuation']['end_to_end']['false_negative'],2)

    def test_unknown_is_not_a_known_speaker(self):
        result=speaker_coverage([dict(speaker_id='s1',text='да'),dict(speaker_id='speaker_unknown',text='ну да')])
        self.assertEqual(result['known_speakers_count'],1)
        self.assertAlmostEqual(result['unknown_word_fraction'],2/3)

    def test_punctuation_empty_and_repeated_marks(self):
        self.assertEqual(punctuation_counts('', '')['end_to_end']['true_positive'],0)
        self.assertEqual(punctuation_counts('«да?!»', '«да?!»')['end_to_end']['true_positive'],4)
        self.assertEqual(punctuation_counts('да...', 'да.')['end_to_end']['false_negative'],2)
        self.assertEqual(punctuation_counts('имя_поля, да.', 'имя поля, да.')['end_to_end']['true_positive'],2)


if __name__ == '__main__':
    unittest.main()
