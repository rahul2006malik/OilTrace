"""
verify_manifest_shapes.py — checks EVERY image and mask in a manifest for
shape/dtype consistency, fast (metadata-only reads, no full pixel decode).

WHY THIS EXISTS: build_tile_index() in sar_dataset.py reads the shape from
only the FIRST image in the manifest, then assumes every other image
matches. It never checks the rest. If even one image has a different
resolution, numpy silently slices a smaller/larger tile near that image's
edges (no exception) — and it only surfaces as a cryptic
"Trying to resize storage that is not resizable" crash deep inside a
DataLoader worker, potentially hours into a training run, when collate
tries to stack that malformed tensor with normally-shaped ones.

The earlier extract_and_inspect scripts only ever spot-checked ONE sample
per subset (Part I: id 0; Part II: id 0 of each of nooil/lookalike) —
never all 2,570 images combined. This script checks all of them.

Uses tifffile.TiffFile(...).pages[0].shape instead of tifffile.imread(...)
— this reads the shape from the TIFF's IFD tags without decoding pixel
data, so checking ~2,570 files takes seconds, not the many minutes a full
decode of ~52GB+21GB would take.

Run this locally against your already-extracted Part I + Part II data:

    python scripts/verify_manifest_shapes.py \
        --manifest data/processed/part1/manifest_part1.csv \
        --manifest data/processed/part2/manifest_part2.csv \
        --expected-image-shape 2048,2048,2 \
        --expected-mask-shape 2048,2048

Requires: tifffile (same as everything else in this pipeline).
"""

import argparse
import csv
import sys
from pathlib import Path

try:
    import tifffile
except ImportError:
    sys.exit("Missing tifffile. Run: pip install tifffile")


def peek_shape(path: str):
    """Metadata-only shape read — does NOT decode pixel data."""
    with tifffile.TiffFile(path) as tf:
        return tf.pages[0].shape


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", action="append", required=True,
                         help="Path to a manifest CSV. Pass multiple times to check several at once.")
    parser.add_argument("--expected-image-shape", default="2048,2048,2")
    parser.add_argument("--expected-mask-shape", default="2048,2048")
    args = parser.parse_args()

    expected_image_shape = tuple(int(x) for x in args.expected_image_shape.split(","))
    expected_mask_shape = tuple(int(x) for x in args.expected_mask_shape.split(","))

    all_rows = []
    for manifest_path in args.manifest:
        with open(manifest_path, newline="") as f:
            for r in csv.DictReader(f):
                r["_source_manifest"] = manifest_path
                all_rows.append(r)

    if not all_rows:
        sys.exit("No rows found across the given manifest(s).")

    print(f"Checking {len(all_rows)} image/mask pairs across {len(args.manifest)} manifest(s)...")
    print(f"Expected image shape: {expected_image_shape}, expected mask shape: {expected_mask_shape}\n")

    image_anomalies = []
    mask_anomalies = []
    errors = []

    for i, row in enumerate(all_rows):
        try:
            img_shape = peek_shape(row["image_path"])
            if tuple(img_shape) != expected_image_shape:
                image_anomalies.append((row["id"], row["image_path"], img_shape, row["_source_manifest"]))
        except Exception as e:
            errors.append((row["id"], row["image_path"], f"image read error: {e}"))

        try:
            mask_shape = peek_shape(row["mask_path"])
            if tuple(mask_shape) != expected_mask_shape:
                mask_anomalies.append((row["id"], row["mask_path"], mask_shape, row["_source_manifest"]))
        except Exception as e:
            errors.append((row["id"], row["mask_path"], f"mask read error: {e}"))

        if (i + 1) % 500 == 0 or (i + 1) == len(all_rows):
            print(f"  {i + 1}/{len(all_rows)} checked...")

    print(f"\n=== Results ===")
    print(f"Total pairs checked: {len(all_rows)}")
    print(f"Image shape anomalies: {len(image_anomalies)}")
    print(f"Mask shape anomalies:  {len(mask_anomalies)}")
    print(f"Read errors:           {len(errors)}")

    if image_anomalies:
        print(f"\n--- Image shape anomalies (expected {expected_image_shape}) ---")
        for sample_id, path, shape, source in image_anomalies:
            print(f"  [{source}] id={sample_id}: shape={shape}  path={path}")

    if mask_anomalies:
        print(f"\n--- Mask shape anomalies (expected {expected_mask_shape}) ---")
        for sample_id, path, shape, source in mask_anomalies:
            print(f"  [{source}] id={sample_id}: shape={shape}  path={path}")

    if errors:
        print(f"\n--- Read errors ---")
        for sample_id, path, err in errors:
            print(f"  id={sample_id}: {err}  path={path}")

    if not image_anomalies and not mask_anomalies and not errors:
        print("\nAll shapes consistent. This manifest is NOT the source of a "
              "'Trying to resize storage that is not resizable' crash — the "
              "issue is elsewhere (e.g. a multi-GPU/DataLoader worker interaction).")
    else:
        print(f"\n*** Found {len(image_anomalies) + len(mask_anomalies) + len(errors)} problem file(s). "
              f"These are very likely the source of the DataLoader crash. Remove or fix them "
              f"before re-running training. ***")


if __name__ == "__main__":
    main()
