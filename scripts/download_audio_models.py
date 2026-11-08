#!/usr/bin/env python3
"""Download pinned ASR/diarization model weights and verify every SHA-256.

Usage examples:
  python scripts/download_audio_models.py --model giga-v3-rnnt
  python scripts/download_audio_models.py --all-missing
  python scripts/download_audio_models.py --check

Network access is required. This script never changes code, manifests, or models
that already match the lock; it only fills or repairs missing model files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "config/audio-models.lock.json"


def model_files(lock, selected):
    catalog = {entry["path"]: entry for entry in lock["files"]}
    result = {}
    for model in lock["models"]:
        if selected and model["id"] not in selected:
            continue
        for path in model["files"]:
            entry = catalog.get(path)
            if entry is None:
                raise ValueError(f"Model lock has no catalog entry for {path}")
            result[path] = entry
    return result


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url, destination, retries=5):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "nuclearhack-model-downloader/1",
                    "Accept": "application/octet-stream",
                },
            )
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
            temporary.replace(destination)
            return
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            temporary.unlink(missing_ok=True)
            if attempt == retries:
                raise RuntimeError(f"download failed after {retries} attempts: {url}: {error}") from error
            sleep_seconds = min(30, 2 ** (attempt - 1))
            print(f"retry {attempt}/{retries} for {url} after {sleep_seconds}s: {error}", flush=True)
            time.sleep(sleep_seconds)


def verify_or_repair(entries, force=False, check_only=False):
    failed = []
    for path, entry in sorted(entries.items()):
        destination = ROOT / path
        expected = entry["sha256"].lower()
        if destination.exists() and not force:
            actual = sha256(destination)
            if actual == expected:
                print(f"OK (already present and verified): {path}")
                continue
            print(f"REPAIR (checksum mismatch): {path}")
        if check_only:
            print(f"MISSING/BAD: {path}")
            failed.append(path)
            continue

        print(f"DOWNLOAD: {path}", flush=True)
        try:
            download(entry["url"], destination)
            actual = sha256(destination)
            if actual != expected:
                raise ValueError(f"SHA-256 mismatch for {path}: got {actual}, expected {expected}")
            print(f"PASS: {path}")
        except Exception as error:  # noqa: BLE001 - report every failed file, then fail.
            print(f"FAIL: {path}: {error}", file=sys.stderr)
            destination.unlink(missing_ok=True)
            destination.with_name(destination.name + ".part").unlink(missing_ok=True)
            failed.append(path)
    return failed


def entry_for_path(lock, path):
    catalog = {entry["path"]: entry for entry in lock["files"]}
    return catalog[path]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", default=[],
                        help="model id from config/audio-models.lock.json; repeatable")
    parser.add_argument("--all-missing", action="store_true",
                        help="process every model with at least one missing/invalid file")
    parser.add_argument("--check", action="store_true",
                        help="do not download; report missing or invalid files")
    parser.add_argument("--force", action="store_true",
                        help="re-download and re-verify files even if SHA matches")
    return parser.parse_args()


def main():
    args = parse_args()
    if not LOCK.is_file():
        raise SystemExit(f"Missing model lock: {LOCK}")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))

    selected = set(args.model)
    if args.all_missing:
        for model in lock["models"]:
            if any(not (ROOT / path).is_file() or sha256(ROOT / path) != entry_for_path(lock, path)["sha256"].lower()
                   for path in model["files"]):
                selected.add(model["id"])
    elif not selected and not args.check:
        # Default to missing models, so a bare run is useful and non-destructive.
        for model in lock["models"]:
            if any(not (ROOT / path).is_file() for path in model["files"]):
                selected.add(model["id"])
    if not selected and not args.check:
        print("All known model files are already present. Use --model to verify/re-download a specific model.")
        return 0

    if args.check:
        selected = set(model["id"] for model in lock["models"])

    entries = model_files(lock, selected)
    if not entries:
        raise SystemExit("No model files selected.")

    print(f"Selected models: {', '.join(sorted(selected)) if selected else '(check all)'}")
    print(f"Files to verify/download: {len(entries)}")
    failed = verify_or_repair(entries, force=args.force, check_only=args.check)
    if failed:
        print(f"\nFAILED: {len(failed)} file(s):", file=sys.stderr)
        for path in failed:
            print(f"  - {path}", file=sys.stderr)
        return 1
    print("\nPASS: all selected model files are present and SHA-256 verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())