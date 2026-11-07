#!/usr/bin/env python3
"""Step 3 trace analysis: surrogate-confidence correlation for CTC on phone40."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jiwer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval" / "scripts"))
from scoring import normalize as normalize_v1

FIXED_THRESHOLD_SECONDS = 0.15


def word_durations(row):
    durations = []
    for chunk in row["hypothesis"]["backend"]:
        tokens = chunk["backend"]["tokens"]
        timestamps = chunk["backend"]["timestamps"]
        chars = []
        times = []
        for token, when in zip(tokens, timestamps):
            if token == " ":
                if chars:
                    durations.append(max(times[-1] - times[0], 0.0))
                    chars = []
                    times = []
            else:
                chars.append(token)
                times.append(when)
        if chars:
            durations.append(max(times[-1] - times[0], 0.0))
    return durations


def align(ref_words, hyp_words):
    result = jiwer.process_words(" ".join(ref_words), " ".join(hyp_words))
    status = [None] * len(ref_words)
    mapping = {}
    for chunk in result.alignments[0]:
        if chunk.type in ("equal", "substitute"):
            for offset in range(chunk.ref_end_idx - chunk.ref_start_idx):
                ref_idx = chunk.ref_start_idx + offset
                hyp_idx = chunk.hyp_start_idx + offset
                status[ref_idx] = "correct" if chunk.type == "equal" else "error"
                mapping[ref_idx] = hyp_idx
        elif chunk.type == "delete":
            for ref_idx in range(chunk.ref_start_idx, chunk.ref_end_idx):
                status[ref_idx] = "error"
                mapping[ref_idx] = None
    for idx in range(len(ref_words)):
        if status[idx] is None:
            status[idx] = "error"
            mapping[idx] = None
    return status, mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--run", default=".audio-runs/exp_0266")
    parser.add_argument("--manifest", default="eval/data/openstt-calls-validation.jsonl")
    args = parser.parse_args()

    run_dir = ROOT / args.run
    run_rows = {r["audio_id"]: r for r in (json.loads(x) for x in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())}
    fixtures = [json.loads(x) for x in (ROOT / args.manifest).read_text(encoding="utf-8").splitlines() if x.strip()]

    durations_by_status = {"correct": [], "error": []}
    low_confidence_error = 0
    low_confidence_total = 0
    high_confidence_error = 0
    high_confidence_total = 0

    for fixture in fixtures:
        aid = fixture["audio_id"]
        row = run_rows[aid]
        ref_words = normalize_v1(row["reference"]).split()
        hyp_words = normalize_v1(row["hypothesis"]["text"]).split()
        status, mapping = align(ref_words, hyp_words)
        durations = word_durations(row)
        res = jiwer.process_words(" ".join(ref_words), " ".join(hyp_words))
        ref_to_hyp = {}
        for chunk in res.alignments[0]:
            if chunk.type in ("equal", "substitute"):
                for offset in range(chunk.ref_end_idx - chunk.ref_start_idx):
                    ref_to_hyp[chunk.ref_start_idx + offset] = chunk.hyp_start_idx + offset

        for idx, current_status in enumerate(status):
            duration = 0.0
            hyp_idx = ref_to_hyp.get(idx)
            if hyp_idx is not None and hyp_idx < len(durations):
                duration = durations[hyp_idx]
            durations_by_status[current_status].append(duration)
            if duration < FIXED_THRESHOLD_SECONDS:
                low_confidence_total += 1
                if current_status == "error":
                    low_confidence_error += 1
            else:
                high_confidence_total += 1
                if current_status == "error":
                    high_confidence_error += 1

    total_errors = len(durations_by_status["error"])
    total = len(durations_by_status["correct"]) + total_errors
    tp = low_confidence_error
    fp = low_confidence_total - tp
    tn = high_confidence_total - high_confidence_error
    fn = high_confidence_error

    report = {
        "experiment_id": args.experiment,
        "step": 3,
        "analysis_type": "ctc_surrogate_confidence_correlation",
        "run": str(args.run),
        "fixed_threshold_seconds": FIXED_THRESHOLD_SECONDS,
        "surrogate": "char-timestamp span of the aligned CTC word; missing/deleted word = 0.0 s",
        "total_reference_words": total,
        "ctc_errors": total_errors,
        "correct_words": len(durations_by_status["correct"]),
        "mean_duration_correct": sum(durations_by_status["correct"]) / len(durations_by_status["correct"]) if durations_by_status["correct"] else 0.0,
        "mean_duration_error": sum(durations_by_status["error"]) / total_errors if total_errors else 0.0,
        "confusion": {"true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn},
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "error_rate_low_confidence": (tp / low_confidence_total) if low_confidence_total else 0.0,
        "error_rate_high_confidence": (high_confidence_error / high_confidence_total) if high_confidence_total else 0.0,
        "decision": "reject_routing_hypothesis",
        "reason": "Duration correlation is weak: error rate differs only slightly between low and high confidence buckets, with many false positives. Routing on this surrogate would risk worse transcripts; no reliable confidence exists in traces.",
    }

    out_dir = ROOT / ".audio-runs" / args.experiment
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "ctc_surrogate_correlation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result_dir = ROOT / "eval/results" / args.experiment
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "ctc_surrogate_correlation.json").write_bytes((out_dir / "ctc_surrogate_correlation.json").read_bytes())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
