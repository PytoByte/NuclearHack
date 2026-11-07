"""Reference metrics must reject partial word lists and invalid source timelines."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_nemo_reference import words_to_transcript
from probe_posterior_attribution import posterior_words
import numpy as np


class ReferenceWords(unittest.TestCase):
    def test_punctuation_and_unknown_speakers_preserve_words(self):
        result = dict(text='Да, привет!', duration=1.2, words=[
            dict(word='Да,', start=0, end=.2, speaker=2),
            dict(word='привет!', start=.3, end=1)])
        words = words_to_transcript(result)
        self.assertEqual([w['speaker_id'] for w in words], ['speaker_2', 'speaker_unknown'])
        self.assertEqual(words[1]['end_ms'], 1000)
        self.assertEqual(' '.join(w['text'] for w in words), result['text'])

    def test_missing_word_cannot_produce_optimistic_cpwer(self):
        with self.assertRaisesRegex(ValueError, 'full transcript'):
            words_to_transcript(dict(text='да нет', duration=1, words=[dict(word='да', start=0, end=.2)]))

    def test_bad_times_are_rejected_instead_of_clipped(self):
        for start, end in [(-.1, .2), (.4, .2), (0, 2), (float('nan'), .2)]:
            with self.subTest(start=start, end=end), self.assertRaisesRegex(ValueError, 'timeline'):
                words_to_transcript(dict(text='да', duration=1, words=[dict(word='да', start=start, end=end)]))


class PosteriorAttribution(unittest.TestCase):
    def test_word_anchor_uses_start_without_rewriting_lexical_text(self):
        probabilities = np.zeros((40, 8), dtype=np.float32)
        probabilities[:16, 1] = .9
        probabilities[16:, 2] = .99
        words = [dict(start_ms=0, end_ms=400, text='длинное')]
        self.assertEqual(posterior_words(words, probabilities, 160)[0]['speaker_id'], 'slot_1')
        self.assertEqual(posterior_words(words, probabilities, 0)[0]['speaker_id'], 'slot_2')
        self.assertEqual(posterior_words(words, probabilities, 160)[0]['text'], 'длинное')

    def test_tail_clamps_to_last_source_frame_and_ties_are_stable(self):
        words = [dict(start_ms=100, end_ms=150, text='да')]
        rows = posterior_words(words, np.zeros((10, 8), dtype=np.float32), 160)
        self.assertEqual(rows[0]['speaker_id'], 'slot_0')
        self.assertEqual(rows[0]['start_ms'], 100)


if __name__ == '__main__': unittest.main()
