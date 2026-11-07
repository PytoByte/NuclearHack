"""Bounded CTC Viterbi alignment of a fixed nonblank token sequence.

Research utility: standard blank-expanded CTC state graph, including mandatory
blank separation for repeated labels. Does not change the supplied transcript.
"""
import numpy as np


def align_tokens(log_probs, tokens, blank=0):
    p = np.asarray(log_probs, dtype=np.float64)
    target = np.asarray(tokens, dtype=np.int64)
    if p.ndim != 2 or not p.shape[0] or not np.isfinite(p).all():
        raise ValueError('Expected finite, nonempty time x vocabulary log probabilities')
    if target.ndim != 1 or not len(target) or np.any(target == blank) or np.any(target < 0) or np.any(target >= p.shape[1]):
        raise ValueError('Expected nonempty nonblank vocabulary IDs')
    if not 0 <= blank < p.shape[1]:
        raise ValueError('Invalid blank')
    states = np.full(2*len(target)+1, blank, dtype=np.int64)
    states[1::2] = target
    skip = np.zeros(len(states), dtype=bool)
    skip[2:] = (states[2:] != blank) & (states[2:] != states[:-2])
    score = np.full(len(states), -np.inf)
    score[0] = p[0, blank]; score[1] = p[0, target[0]]
    back = np.zeros((len(p), len(states)), dtype=np.uint8)
    for t in range(1, len(p)):
        advance = np.concatenate(([-np.inf], score[:-1]))
        jump = np.concatenate(([-np.inf, -np.inf], score[:-2]))
        jump[~skip] = -np.inf
        candidates = np.stack((score, advance, jump))
        step = candidates.argmax(axis=0)
        back[t] = step
        score = candidates[step, np.arange(len(states))] + p[t, states]
    state = len(states)-2 + int(score[-1] > score[-2])
    if not np.isfinite(score[state]):
        raise ValueError('CTC target has no feasible path')
    best = float(score[state])
    path = np.empty(len(p), dtype=np.int32)
    for t in range(len(p)-1, -1, -1):
        path[t] = state
        state -= int(back[t, state])
    spans = []
    for i in range(len(target)):
        frames = np.flatnonzero(path == 2*i+1)
        if not len(frames):
            raise ValueError('Incomplete CTC path')
        spans.append((int(frames[0]), int(frames[-1])+1))
    return spans, best
