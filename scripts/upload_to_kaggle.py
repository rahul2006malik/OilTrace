"""
upload_to_kaggle.py — chunked, resumable Kaggle dataset upload.

WHY CHUNKED: a single `kaggle datasets create` call on a 50GB+ folder has
no meaningful resume point if it dies partway (network drop, laptop
sleep, terminal closed) — you're very likely re-uploading everything from
byte zero. This script instead splits your manifest into small batches
(a few GB each, one Kaggle Dataset per batch) and tracks which batches
have already succeeded in a state file, so re-running the script after a
failure or interruption only retries the batch(es) that didn't finish —
nothing already-uploaded gets redone.

REUSABLE for Part II / Part III later — just point --data-dir,
--manifest, and --slug-prefix at the new part.

Usage:
    pip install kaggle
    # kaggle.json (from kaggle.com/settings -> API -> Create New Token)
    # must be at C:\\Users\\<you>\\.kaggle\\kaggle.json on Windows

    python upload_to_kaggle.py --data-dir data/processed/part1 ^
        --manifest data/processed/part1/manifest_part1.csv ^
        --slug-prefix oiltrace-part1 --batch-size 150

PROGRESS: this script prints "[i/N] batchNNNN: ..." before each batch.
Within a batch, Kaggle's own CLI prints its native per-file progress bars
directly to your terminal — this script does not capture or hide that
output, so you see real upload progress, not just a spinner.

RESUMING after a failure or interruption: run the exact same command
again. Batches already recorded as "done" in _upload_state.json (next to
your manifest) are skipped instantly; the batch that was interrupted
retries from scratch (that's the "blast radius" of one batch — a few GB,
not the whole dataset). If a batch fails --max-retries times in a row,
the script stops and tells you which batch to look at.

FIXES applied after the first real run (which finished suspiciously fast):
  1. `kaggle datasets create` silently SKIPS subfolders (images/, masks/)
     unless given --dir-mode zip — it printed "Skipping folder: ...; use
     '--dir-mode'" and exited 0. That looked like success but only the
     tiny manifest CSV actually uploaded each time. Now always passed.
  2. Because of (1), the 8 "datasets" from that first run already exist
     on Kaggle as empty stubs (manifest only, no images/masks). Re-running
     against an existing dataset needs `kaggle datasets version`, not
     `create` (which now correctly errors "already exists" instead of
     silently no-opping). This script checks first and picks automatically
     — safe whether the dataset is a fresh stub or doesn't exist yet.

ONE-TIME MANUAL STEP if you're recovering from that first bad run:
     delete (or rename) _upload_state.json next to your manifest before
     rerunning. It currently records all 8 batches as "done" from the
     first run's false-positive exit code 0 — leaving it in place would
     make this script skip every batch instead of actually uploading the
     real images/masks this time.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def sanitize_slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def get_kaggle_username() -> str:
    cfg_path = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle")) / "kaggle.json"
    if not cfg_path.exists():
        sys.exit(
            f"Couldn't find {cfg_path}. Download an API token from "
            f"kaggle.com/settings -> API -> Create New Token, and place "
            f"kaggle.json there before running this script."
        )
    with open(cfg_path) as f:
        return json.load(f)["username"]


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        with open(state_path) as f:
            return json.load(f)
    return {}


def save_state(state_path: Path, state: dict) -> None:
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def make_batch_dir(rows: list[dict], batch_dir: Path) -> None:
    images_dir = batch_dir / "images"
    masks_dir = batch_dir / "masks"
    images_dir.mkdir(parents=True, exist_ok=True)
    masks_dir.mkdir(parents=True, exist_ok=True)

    batch_rows = []
    used_img_names: dict[str, str] = {}
    used_mask_names: dict[str, str] = {}

    for row in rows:
        img_src = Path(row["image_path"])
        mask_src = Path(row["mask_path"])

        # Fallback if relative paths are relative to repo root rather than current working directory
        if not img_src.exists() and (batch_dir.parent.parent / img_src).exists():
            img_src = batch_dir.parent.parent / img_src
        if not mask_src.exists() and (batch_dir.parent.parent / mask_src).exists():
            mask_src = batch_dir.parent.parent / mask_src

        # Disambiguate if duplicate filename exists in the same batch from different source files
        img_dst_name = img_src.name
        img_src_resolved = str(img_src.resolve()) if img_src.exists() else str(img_src)
        if img_dst_name in used_img_names and used_img_names[img_dst_name] != img_src_resolved:
            img_dst_name = f"{row['id']}_{img_src.name}"
        used_img_names[img_dst_name] = img_src_resolved

        mask_dst_name = mask_src.name
        mask_src_resolved = str(mask_src.resolve()) if mask_src.exists() else str(mask_src)
        if mask_dst_name in used_mask_names and used_mask_names[mask_dst_name] != mask_src_resolved:
            mask_dst_name = f"{row['id']}_{mask_src.name}"
        used_mask_names[mask_dst_name] = mask_src_resolved

        img_dst = images_dir / img_dst_name
        mask_dst = masks_dir / mask_dst_name

        # Hardlinks, not copies — same volume, so this is instant and uses
        # no extra disk space. Falls back to a real copy only if
        # hardlinking isn't possible (e.g. paths on different drives).
        for src, dst in [(img_src, img_dst), (mask_src, mask_dst)]:
            if dst.exists():
                continue
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)

        row_dict = {
            "id": row["id"],
            "image_path": f"images/{img_dst.name}",
            "mask_path": f"masks/{mask_dst.name}",
        }
        for k, v in row.items():
            if k not in row_dict:
                row_dict[k] = v
        batch_rows.append(row_dict)

    fieldnames = list(batch_rows[0].keys()) if batch_rows else ["id", "image_path", "mask_path"]
    with open(batch_dir / f"manifest_{batch_dir.name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(batch_rows)


def write_metadata(batch_dir: Path, username: str, slug: str) -> None:
    metadata = {
        "title": slug,
        "id": f"{username}/{slug}",
        "licenses": [{"name": "CC0-1.0"}],
    }
    with open(batch_dir / "dataset-metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)


def dataset_exists(username: str, slug: str) -> bool:
    """Cheap status check (output captured, not streamed) used only to
    decide which upload command to use — NOT the real upload call, so
    capturing its output here doesn't hide any real progress bars.
    """
    result = subprocess.run(
        ["kaggle", "datasets", "status", f"{username}/{slug}"],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def upload_batch(batch_dir: Path, username: str, slug: str, max_retries: int, retry_wait: int) -> bool:
    # BUG FIX: `kaggle datasets create` silently SKIPS subfolders unless
    # told otherwise — it printed "Skipping folder: images/masks; use
    # '--dir-mode'" and exited 0, which looked like success but uploaded
    # almost nothing. --dir-mode zip zips each subfolder before upload,
    # which is also far more efficient than thousands of individual files.
    #
    # BUG FIX #2: if this batch's dataset slug already exists on Kaggle
    # (e.g. from a prior run that only uploaded the stub manifest), `create`
    # fails with "dataset already exists" — the real command for adding
    # data to an existing dataset is `kaggle datasets version`. We check
    # first and pick the right command, so this script is safe to rerun
    # against partially-uploaded stub datasets AND safe to use fresh for
    # Part II/III later.
    exists = dataset_exists(username, slug)
    if exists:
        cmd = ["kaggle", "datasets", "version", "-p", str(batch_dir),
               "-m", "Add full images/masks data", "--dir-mode", "zip"]
    else:
        cmd = ["kaggle", "datasets", "create", "-p", str(batch_dir), "--dir-mode", "zip"]

    for attempt in range(1, max_retries + 1):
        print(f"\n--- Uploading {batch_dir.name} as {'version update to' if exists else 'new dataset'} "
              f"{username}/{slug} (attempt {attempt}/{max_retries}) ---")
        # Not capturing stdout/stderr — this lets Kaggle's own per-file
        # progress bars print straight to your terminal.
        result = subprocess.run(cmd)
        if result.returncode == 0:
            return True
        print(f"Attempt {attempt} failed (exit code {result.returncode}).")
        if attempt < max_retries:
            print(f"Retrying in {retry_wait}s...")
            time.sleep(retry_wait)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True,
                         help="Folder containing images/, masks/, and the manifest (used to resolve state-file location).")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--slug-prefix", required=True,
                         help="e.g. oiltrace-part1 — a batch number gets appended to form each dataset slug.")
    parser.add_argument("--batch-size", type=int, default=150,
                         help="Images per batch. ~150 images is ~6-7GB for this dataset's average file sizes.")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-wait", type=int, default=30, help="Seconds between retries.")
    parser.add_argument("--batches-dir", default=None,
                         help="Where to stage batch folders (hardlinks). Defaults to <data-dir>/_batches.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    manifest_path = Path(args.manifest)
    slug_prefix = sanitize_slug(args.slug_prefix)
    batches_dir = Path(args.batches_dir) if args.batches_dir else data_dir / "_batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    state_path = data_dir / "_upload_state.json"

    username = get_kaggle_username()

    with open(manifest_path, newline="") as f:
        rows = list(csv.DictReader(f))

    batches = [rows[i:i + args.batch_size] for i in range(0, len(rows), args.batch_size)]
    state = load_state(state_path)

    print(f"{len(rows)} images -> {len(batches)} batches of up to {args.batch_size} images each.")
    print(f"Already done: {sum(1 for v in state.values() if v == 'done')}/{len(batches)}\n")

    for idx, batch_rows in enumerate(batches, start=1):
        batch_name = f"batch{idx:04d}"
        slug = f"{slug_prefix}-{batch_name}"

        if state.get(batch_name) == "done":
            print(f"[{idx}/{len(batches)}] {batch_name}: already uploaded, skipping.")
            continue

        print(f"[{idx}/{len(batches)}] {batch_name}: preparing {len(batch_rows)} images...")
        batch_dir = batches_dir / batch_name
        make_batch_dir(batch_rows, batch_dir)
        write_metadata(batch_dir, username, slug)

        ok = upload_batch(batch_dir, username, slug, args.max_retries, args.retry_wait)
        state[batch_name] = "done" if ok else "failed"
        save_state(state_path, state)

        if not ok:
            print(f"\n{batch_name} failed after {args.max_retries} attempts. "
                  f"State saved to {state_path} — re-run this exact command "
                  f"later to retry just this batch. Earlier batches will be "
                  f"skipped, not re-uploaded.")
            sys.exit(1)

    print(f"\nAll {len(batches)} batches uploaded. Kaggle dataset slugs:")
    for idx in range(1, len(batches) + 1):
        print(f"  {username}/{slug_prefix}-batch{idx:04d}")
    print("\nAdd all of these as inputs to your Kaggle notebook, then run "
          "combine_kaggle_manifests.py there to stitch them into one manifest.")


if __name__ == "__main__":
    main()
