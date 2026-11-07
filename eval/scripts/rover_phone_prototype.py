#!/usr/bin/env python3
"""Step 2 screening: simple word-level ROVER on saved phone40 traces.

Two systems only; differing votes use CTC as the tie-break because no reliable
per-word confidence is available. No ASR inference is run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scoring import counts, normalize

ROOT = Path(__file__).resolve().parents[2]


def load_run(path):
    run = Path(path)
    rows = {r["audio_id"]: r for r in (json.loads(x) for x in (run / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())}
    return rows


def align(ref_words, hyp_words):
    # Minimal position mapping compatible with jiwer.process_words via align_to_reference logic.
    import jiwer
    result = jiwer.process_words(" ".join(ref_words), " ".join(hyp_words))
    status = [None] * len(ref_words)
    word = [None] * len(ref_words)
    insertions = []
    for chunk in result.alignments[0]:
        if chunk.type == "equal":
            for o in range(chunk.ref_end_idx - chunk.ref_start_idx):
                status[chunk.ref_start_idx + o] = "correct"
                word[chunk.ref_start_idx + o] = hyp_words[chunk.hyp_start_idx + o]
        elif chunk.type == "substitute":
            for o in range(chunk.ref_end_idx - chunk.ref_start_idx):
                status[chunk.ref_start_idx + o] = "substitution"
                word[chunk.ref_start_idx + o] = hyp_words[chunk.hyp_start_idx + o]
        elif chunk.type == "delete":
            for i in range(chunk.ref_start_idx, chunk.ref_end_idx):
                status[i] = "deletion"
                word[i] = None
        elif chunk.type == "insert":
            insertions.extend(hyp_words[chunk.hyp_start_idx:chunk.hyp_end_idx])
    for i in range(len(ref_words)):
        if status[i] is None:
            status[i] = "deletion"
            word[i] = None
    return status, word, insertions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--manifest", default="eval/data/openstt-calls-validation.jsonl")
    parser.add_argument("--ctc-run", default=".audio-runs/exp_0266")
    parser.add_argument("--rnnt-run", default=".audio-runs/exp_0265")
    args = parser.parse_args()

    manifest = [json.loads(line) for line in (ROOT / args.manifest).read_text(encoding="utf-8").splitlines() if line.strip()]
    ctc_rows = load_run(ROOT / args.ctc_run)
    rnnt_rows = load_run(ROOT / args.rnnt_run)

    fused_rows = []
    for fixture in manifest:
        audio_id = fixture["audio_id"]
        reference = ctc_rows[audio_id]["reference"]
        ref_words = normalize(reference).split()
        ctc_hyp = normalize(ctc_rows[audio_id]["hypothesis"]["text"]).split()
        rnnt_hyp = normalize(rnnt_rows[audio_id]["hypothesis"]["text"]).split()
        ctc_status, ctc_word, ctc_insertions = align(ref_words, ctc_hyp)
        rnnt_status, rnnt_word, rnnt_insertions = align(ref_words, rnnt_hyp)

        fused_words = []
        for index in range(len(ref_words)):
            # CTC tie-break: if CTC has a token, use it; otherwise delete.
            if ctc_word[index] is not None:
                fused_words.append(ctc_word[index])
            else:
                continue
        # Preserve the CTC insertion count instead of artificially dropping insertions.
        fused_words.extend(ctc_insertions)
        fused_text = " ".join(fused_words)

        fused_rows.append({
            "audio_id": audio_id,
            "reference": reference,
            "hypothesis": fused_text,
            "normalized": counts(reference, fused_text),
            "raw": counts(reference, fused_text, False),
            "ctc_insertions": len(ctc_insertions),
            "rnnt_insertions": len(rnnt_insertions),
        })

    total = {
        "substitutions": sum(r["normalized"]["substitutions"] for r in fused_rows),
        "deletions": sum(r["normalized"]["deletions"] for r in fused_rows),
        "insertions": sum(r["normalized"]["insertions"] for r in fused_rows),
        "reference_words": sum(r["normalized"]["reference_words"] for r in fused_rows),
    }
    total["wer"] = (total["substitutions"] + total["deletions"] + total["insertions"]) / total["reference_words"]

    out = ROOT / ".audio-runs" / args.experiment
    out.mkdir(parents=True, exist_ok=False)
    (out / "per_file.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in fused_rows), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps({
        "experiment_id": args.experiment,
        "scope": "phone40 ROVER screening, CTC tie-break, no confidence available",
        "baseline_ctc_wer": 0.17647058823529413,
        "baseline_rnnt_wer": 0.1642156862745098,
        "fused": total,
        "ctc_insertions": sum(r["ctc_insertions"] for r in fused_rows),
        "rnnt_insertions": sum(r["rnnt_insertions"] for r in fused_rows),
        "accept_rule": "WER fused < 0.1642156862745098 and insertions not grow by more than 1-2 absolute",
        "decision": "reject_no_quality_gain" if total["wer"] >= 0.1642156862745098 else "accept_for_further_check",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = ROOT / "eval/results" / args.experiment
    report.mkdir(parents=True, exist_ok=True)
    (report / "metrics.json").write_bytes((out / "metrics.json").read_bytes())

    print(json.dumps({"fused_wer": total["wer"], "substitutions": total["substitutions"],
                      "deletions": total["deletions"], "insertions": total["insertions"],
                      "reference_words": total["reference_words"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())