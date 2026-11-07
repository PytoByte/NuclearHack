"""Fixed normalization v1. Numbers remain as written; fillers are retained."""
import unicodedata
import re
from collections import Counter
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


# Policy v2 is additive: existing normalization v1 and historic scores stay fixed.
PUNCTUATION = '.,?!:;—-…«»"()'


def punctuation_slots(text):
    """Normalize lexical tokens, attach marks to the preceding word (or BOS)."""
    words, marks = [], []
    for token in re.findall(r'\w+|[^\w\s]', unicodedata.normalize('NFC', text), re.UNICODE):
        if token in PUNCTUATION:
            marks.append((len(words) - 1, token))
        elif any(c.isalnum() for c in token):
            words.extend(normalize(token).split())
    return words, marks


def punctuation_counts(reference, hypothesis):
    """Marks match only at equal-word alignment anchors, never by absolute index.

    Marks after substituted/deleted words are FN; after inserted/substituted
    hypothesis words are FP. BOS is a shared anchor. Case is not punctuation.
    """
    a, am = punctuation_slots(reference); b, bm = punctuation_slots(hypothesis)
    alignment = jiwer.process_words(' '.join(a), ' '.join(b))
    anchors = {-1: -1}; matched = {-1}
    for chunk in alignment.alignments[0]:
        if chunk.type == 'equal':
            for i, j in zip(range(chunk.ref_start_idx, chunk.ref_end_idx),
                            range(chunk.hyp_start_idx, chunk.hyp_end_idx)):
                anchors[j] = i; matched.add(i)
    truth = Counter(am)
    prediction = Counter((anchors.get(i, ('unmatched_hyp', i)), p) for i, p in bm)
    def score(left, right):
        return dict(true_positive=sum((left & right).values()),
                    false_positive=sum((right - left).values()), false_negative=sum((left - right).values()))
    return dict(end_to_end=score(truth, prediction),
        conditional_equal_words=score(Counter({k:v for k,v in truth.items() if k[0] in matched}),
            Counter({k:v for k,v in prediction.items() if k[0] in matched})),
        per_mark={p:score(Counter({k:v for k,v in truth.items() if k[1]==p}),
                          Counter({k:v for k,v in prediction.items() if k[1]==p})) for p in PUNCTUATION})


def text_metrics(reference, hypothesis):
    def punct_tokens(s):
        return ' '.join(re.findall(r'\w+|[^\w\s]', unicodedata.normalize('NFC',s).lower().replace('ё','е')))
    def cer(left, right):
        c=jiwer.process_characters(left,right)
        return dict(errors=c.substitutions+c.deletions+c.insertions,
                    reference_characters=c.hits+c.substitutions+c.deletions)
    return dict(policy='text-v2', normalized=counts(reference,hypothesis), raw=counts(reference,hypothesis,False),
        punctuation_token_wer=counts(punct_tokens(reference),punct_tokens(hypothesis),False),
        normalized_cer=cer(normalize(reference),normalize(hypothesis)),raw_cer=cer(reference,hypothesis),
        punctuation=punctuation_counts(reference,hypothesis))


def speaker_coverage(transcript):
    unknown=[t for t in transcript if t['speaker_id']=='speaker_unknown']
    words=sum(len(normalize(t['text']).split()) for t in transcript)
    return dict(known_speakers_count=len({t['speaker_id'] for t in transcript if t['speaker_id']!='speaker_unknown'}),
        unknown_utterances=len(unknown),unknown_utterance_fraction=len(unknown)/len(transcript) if transcript else 0,
        unknown_word_fraction=sum(len(normalize(t['text']).split()) for t in unknown)/words if words else 0,
        predicted_speakers_includes_unknown=True)
