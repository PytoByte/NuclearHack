"""Fixed normalization v1. Numbers remain as written; fillers are retained."""
import unicodedata
import jiwer


def normalize(text):
    text = unicodedata.normalize('NFC', text).lower().replace('ё', 'е')
    return ' '.join(''.join(' ' if unicodedata.category(c).startswith(('P', 'S')) else c for c in text).split())


def counts(reference, hypothesis, normalized=True):
    if normalized:
        reference, hypothesis = normalize(reference), normalize(hypothesis)
    result = jiwer.process_words(reference, hypothesis)
    return dict(substitutions=result.substitutions, deletions=result.deletions,
                insertions=result.insertions, reference_words=result.hits + result.substitutions + result.deletions)


def aggregate(rows):
    total = {k: sum(row[k] for row in rows) for k in ('substitutions', 'deletions', 'insertions', 'reference_words')}
    total['wer'] = (total['substitutions'] + total['deletions'] + total['insertions']) / total['reference_words'] if total['reference_words'] else None
    return total
