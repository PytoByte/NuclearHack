#!/usr/bin/env python3
"""Step 1: word-level error overlap between two saved ASR runs.

Input runs must be produced by eval/scripts/run_asr.py and contain
results.jsonl with normalized reference and hypothesis text. The script
performs no ASR inference.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import jiwer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval" / "scripts"))
from scoring import normalize as normalize_v1


def load_run(run_dir):
    run_dir = Path(run_dir)
    config_path = run_dir / "config.json"
    results_path = run_dir / "results.jsonl"
    if not config_path.is_file() or not results_path.is_file():
        raise ValueError(f"Run is missing config.json/results.jsonl: {run_dir}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"Empty results.jsonl: {run_dir}")
    rows_by_audio = {row["audio_id"]: row for row in rows}
    if len(rows_by_audio) != len(rows):
        raise ValueError(f"Duplicate audio_id in {run_dir}")
    return config, rows_by_audio


def align_to_reference(ref_words, hyp_words):
    if not ref_words:
        return [], {"substitutions": 0, "deletions": 0, "insertions": 0, "hits": 0}
    result = jiwer.process_words(" ".join(ref_words), " ".join(hyp_words))
    status = [None] * len(ref_words)          # correct / substitution / deletion
    hyp_word = [None] * len(ref_words)         # None for deletion
    insertions = []

    for chunk in result.alignments[0]:
        if chunk.type == "equal":
            for offset in range(chunk.ref_end_idx - chunk.ref_start_idx):
                ref_index = chunk.ref_start_idx + offset
                hyp_index = chunk.hyp_start_idx + offset
                status[ref_index] = "correct"
                hyp_word[ref_index] = hyp_words[hyp_index]
        elif chunk.type == "substitute":
            for offset in range(chunk.ref_end_idx - chunk.ref_start_idx):
                ref_index = chunk.ref_start_idx + offset
                hyp_index = chunk.hyp_start_idx + offset
                status[ref_index] = "substitution"
                hyp_word[ref_index] = hyp_words[hyp_index]
        elif chunk.type == "delete":
            for ref_index in range(chunk.ref_start_idx, chunk.ref_end_idx):
                status[ref_index] = "deletion"
                hyp_word[ref_index] = None
        elif chunk.type == "insert":
            for hyp_index in range(chunk.hyp_start_idx, chunk.hyp_end_idx):
                insertions.append(hyp_words[hyp_index])

    for index in range(len(ref_words)):
        if status[index] is None:
            status[index] = "deletion"
            hyp_word[index] = None
    return status, hyp_word, insertions, {
        "substitutions": result.substitutions,
        "deletions": result.deletions,
        "insertions": result.insertions,
        "hits": result.hits,
        "reference_words": len(ref_words),
    }


def classify_pair(primary_status, secondary_status, primary_word, secondary_word, ref_word):
    if primary_status == "correct" and secondary_status == "correct":
        return "both_correct"
    if primary_status == "correct" and secondary_status != "correct":
        return "primary_correct_secondary_error"
    if primary_status != "correct" and secondary_status == "correct":
        return "primary_error_secondary_correct"
    # Both erred.
    if primary_status == "deletion" and secondary_status == "deletion":
        return "both_deletion"
    if primary_status == "substitution" and secondary_status == "substitution":
        if primary_word == secondary_word:
            return "both_substitution_same"
        return "both_substitution_different"
    return "mixed_type"


def analyze_domain(domain, manifest_path, primary_run, secondary_run, primary_id, secondary_id):
    manifest_path = Path(manifest_path)
    fixtures = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    primary_config, primary_rows = load_run(primary_run)
    secondary_config, secondary_rows = load_run(secondary_run)

    category_counts = {
        "both_correct": 0,
        "primary_correct_secondary_error": 0,
        "primary_error_secondary_correct": 0,
        "both_deletion": 0,
        "both_substitution_same": 0,
        "both_substitution_different": 0,
        "mixed_type": 0,
    }
    per_clip = []
    union_error_positions = 0
    one_correct_positions = 0
    both_error_positions = 0
    different_replacement_positions = 0

    primary_totals = {"substitutions": 0, "deletions": 0, "insertions": 0, "reference_words": 0}
    secondary_totals = {"substitutions": 0, "deletions": 0, "insertions": 0, "reference_words": 0}

    rescue_primary_deletions = 0
    rescue_secondary_deletions = 0
    for fixture in fixtures:
        audio_id = fixture["audio_id"]
        if audio_id not in primary_rows or audio_id not in secondary_rows:
            raise ValueError(f"{audio_id} missing from one of the runs")
        primary_reference = normalize_v1(primary_rows[audio_id]["reference"])
        secondary_reference = normalize_v1(secondary_rows[audio_id]["reference"])
        if primary_reference != secondary_reference:
            raise ValueError(f"Reference text differs between runs for {audio_id}")
        reference = primary_reference
        ref_words = reference.split()
        primary_text = normalize_v1(primary_rows[audio_id]["hypothesis"]["text"])
        secondary_text = normalize_v1(secondary_rows[audio_id]["hypothesis"]["text"])

        primary_status, primary_word, primary_insertions, primary_counts = align_to_reference(
            ref_words, primary_text.split())
        secondary_status, secondary_word, secondary_insertions, secondary_counts = align_to_reference(
            ref_words, secondary_text.split())

        clip_categories = {key: 0 for key in category_counts}
        differing_examples = []
        for index, ref_word in enumerate(ref_words):
            category = classify_pair(
                primary_status[index], secondary_status[index],
                primary_word[index], secondary_word[index], ref_word)
            category_counts[category] += 1
            clip_categories[category] += 1
            if primary_status[index] != "correct" or secondary_status[index] != "correct":
                union_error_positions += 1
            if (primary_status[index] == "correct") != (secondary_status[index] == "correct"):
                one_correct_positions += 1
            if primary_status[index] != "correct" and secondary_status[index] != "correct":
                both_error_positions += 1
                if category in ("both_substitution_different", "mixed_type"):
                    different_replacement_positions += 1
            if primary_status[index] == "deletion" and secondary_status[index] != "deletion":
                rescue_primary_deletions += 1
            if secondary_status[index] == "deletion" and primary_status[index] != "deletion":
                rescue_secondary_deletions += 1
            if (primary_status[index] != secondary_status[index]
                    or (primary_status[index] == "substitution"
                        and secondary_status[index] == "substitution"
                        and primary_word[index] != secondary_word[index])):
                differing_examples.append({
                    "reference_word": ref_word,
                    f"{primary_id}_status": primary_status[index],
                    f"{primary_id}_word": primary_word[index],
                    f"{secondary_id}_status": secondary_status[index],
                    f"{secondary_id}_word": secondary_word[index],
                })

        primary_totals = {key: primary_totals[key] + primary_counts[key] for key in primary_totals}
        secondary_totals = {key: secondary_totals[key] + secondary_counts[key] for key in secondary_totals}

        per_clip.append({
            "audio_id": audio_id,
            "reference_words": len(ref_words),
            "categories": clip_categories,
            "differing_positions": len(differing_examples),
            f"{primary_id}_insertions": len(primary_insertions),
            f"{secondary_id}_insertions": len(secondary_insertions),
            "examples": differing_examples[:12],
        })

    total_ref_words = sum(len(normalize_v1(primary_rows[f["audio_id"]]["reference"]).split()) for f in fixtures)

    categories_with_fraction = {}
    for key, count in category_counts.items():
        categories_with_fraction[key] = {
            "count": count,
            "fraction_of_reference_words": count / total_ref_words if total_ref_words else 0.0,
            "fraction_of_union_error_positions": count / union_error_positions if union_error_positions else 0.0,
        }

    union_errors = union_error_positions
    one_correct_fraction = one_correct_positions / union_errors if union_errors else 0.0
    differing_fraction = (one_correct_positions + different_replacement_positions) / union_errors if union_errors else 0.0

    # Predefined conservative threshold: at least 15% of union error positions are
    # "one correct, one wrong"; counts both wrong-but-different as additional support.
    green_light = one_correct_fraction >= 0.15 and union_errors > 0

    return {
        "domain": domain,
        "manifest": str(manifest_path.relative_to(ROOT)) if manifest_path.is_relative_to(ROOT) else str(manifest_path),
        "clips": len(fixtures),
        "reference_words": total_ref_words,
        "models": {
            primary_id: {
                "run_dir": str(primary_run),
                "config_model": primary_config.get("model"),
                "aggregate": primary_totals,
            },
            secondary_id: {
                "run_dir": str(secondary_run),
                "config_model": secondary_config.get("model"),
                "aggregate": secondary_totals,
            },
        },
        "union_error_positions": union_errors,
        "categories": categories_with_fraction,
        "fractions": {
            "one_correct_of_union_errors": one_correct_fraction,
            "one_correct_plus_different_replacement_of_union_errors": differing_fraction,
        },
        "deletion_rescue": {
            f"{primary_id}_deletions_rescued_by_{secondary_id}": rescue_primary_deletions,
            f"{secondary_id}_deletions_rescued_by_{primary_id}": rescue_secondary_deletions,
            "note": "A deletion is considered rescued if the other system has a word (correct or substitution) at the same reference position.",
        },
        "green_light": green_light,
        "green_light_rule": "Go to Step 2 only if at least 15% of union error positions are corrected by one model while the other errs; report below if not.",
        "per_clip": per_clip,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--primary-id", default="ctc")
    parser.add_argument("--secondary-id", default="rnnt")
    parser.add_argument("--pair", action="append", required=True,
                        help="DOMAIN=MANIFEST=PRIMARY_RUN=SECONDARY_RUN")
    args = parser.parse_args()

    if not args.experiment.startswith("exp_") or not args.experiment[4:].isdigit():
        parser.error("Use exp_NNNN")

    domains = []
    for spec in args.pair:
        parts = spec.split("=", 3)
        if len(parts) != 4:
            parser.error("--pair must be DOMAIN=MANIFEST=PRIMARY_RUN=SECONDARY_RUN")
        domain, manifest, primary_run, secondary_run = (part.strip() for part in parts)
        domains.append(analyze_domain(
            domain, manifest, primary_run, secondary_run,
            args.primary_id, args.secondary_id))

    overall_green = any(domain["green_light"] for domain in domains)
    result = {
        "experiment_id": args.experiment,
        "step": 1,
        "analysis_type": "error_overlap_without_asr_inference",
        "systems": {
            args.primary_id: "primary input run",
            args.secondary_id: "secondary input run",
        },
        "domains": domains,
        "overall_green_light": overall_green,
        "decision": "go_to_step_2_prototype" if overall_green else "reject_rover_hypothesis",
        "note": "Decision is based on provided saved ASR runs only; no new ASR inference was performed by this script.",
    }

    out_dir = ROOT / ".audio-runs" / args.experiment
    out_dir.mkdir(parents=True, exist_ok=False)
    output_path = out_dir / "error_overlap.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_dir = ROOT / "eval/results" / args.experiment
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "error_overlap.json").write_bytes(output_path.read_bytes())

    print(json.dumps({
        "experiment": args.experiment,
        "domains": [
            {
                "domain": domain["domain"],
                "reference_words": domain["reference_words"],
                "union_error_positions": domain["union_error_positions"],
                "one_correct_fraction": domain["fractions"]["one_correct_of_union_errors"],
                "green_light": domain["green_light"],
            }
            for domain in domains
        ],
        "overall_green_light": overall_green,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())