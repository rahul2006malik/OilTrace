"""
combine_kaggle_manifests.py — run this in a Kaggle notebook cell, once,
before train_unet.py.

Because the data was uploaded as several small batch datasets (see
upload_to_kaggle.py) instead of one giant one, each batch dataset mounts
separately under /kaggle/input/<slug>/ and carries its own small manifest
with paths relative to itself. This script finds every batch dataset
matching any of the given --slug-prefix values, rewrites each row's
image_path/mask_path to the correct absolute /kaggle/input/... path, and
writes ONE combined manifest that train_unet.py's --manifest can point at
directly.

UPDATED: --slug-prefix now accepts multiple values, so Part I and Part II
(and Part III, if you ever need it combined) can be merged in a single
call instead of running this twice and stitching CSVs by hand.

Usage (in a Kaggle notebook cell) — single part, same as before:
    !python combine_kaggle_manifests.py --slug-prefix oiltrace-part1 \
        --output /kaggle/working/manifest_part1_combined.csv

Usage — merging Part I + Part II into one training manifest:
    !python combine_kaggle_manifests.py --slug-prefix oiltrace-part1 oiltrace-part2 \
        --output /kaggle/working/manifest_train_combined.csv

If your datasets mount nested (e.g. /kaggle/input/datasets/<username>/...
instead of directly under /kaggle/input/), pass --kaggle-input pointed at
the real parent folder, same as before.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug-prefix", required=True, nargs="+",
                         help="One or more prefixes, e.g. --slug-prefix oiltrace-part1 oiltrace-part2. "
                              "Each is the same value you passed to upload_to_kaggle.py for that part.")
    parser.add_argument("--kaggle-input", default="/kaggle/input")
    parser.add_argument("--output", default="/kaggle/working/manifest_combined.csv")
    args = parser.parse_args()

    all_rows = []
    per_prefix_counts = {}

    for prefix in args.slug_prefix:
        batch_dirs = sorted(
            d for d in glob.glob(os.path.join(args.kaggle_input, f"{prefix}-batch*"))
            if os.path.isdir(d)
        )
        if not batch_dirs:
            raise SystemExit(
                f"No mounted datasets matching '{prefix}-batch*' found under "
                f"{args.kaggle_input}. Did you add all the batch datasets for '{prefix}' as notebook inputs? "
                f"(Already-combined prefixes so far: {list(per_prefix_counts.keys())})"
            )

        prefix_row_count = 0
        for batch_dir in batch_dirs:
            manifests = glob.glob(os.path.join(batch_dir, "manifest_batch*.csv"))
            if not manifests:
                print(f"WARNING: no manifest_batch*.csv found in {batch_dir}, skipping.")
                continue
            with open(manifests[0], newline="") as f:
                for r in csv.DictReader(f):
                    all_rows.append({
                        "id": r["id"],
                        "image_path": os.path.join(batch_dir, r["image_path"]),
                        "mask_path": os.path.join(batch_dir, r["mask_path"]),
                        "source_prefix": prefix,
                    })
                    prefix_row_count += 1
        per_prefix_counts[prefix] = prefix_row_count
        print(f"'{prefix}': {prefix_row_count} images from {len(batch_dirs)} batch datasets.")

    # Sanity check: ids should be unique across ALL merged prefixes. Part
    # I uses plain numeric ids, Part II uses lookalike_/nooil_ prefixed
    # ids specifically so this can never collide — but check anyway rather
    # than trust that convention silently held.
    all_ids = [r["id"] for r in all_rows]
    if len(all_ids) != len(set(all_ids)):
        dupes = {i for i in all_ids if all_ids.count(i) > 1}
        raise SystemExit(
            f"Found {len(dupes)} duplicate id(s) across merged prefixes — refusing to write a "
            f"manifest with ambiguous ids. Examples: {list(dupes)[:5]}"
        )

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "image_path", "mask_path", "source_prefix"])
        w.writeheader()
        w.writerows(all_rows)

    print(f"\nCombined {len(all_rows)} images total from {len(args.slug_prefix)} prefix(es) -> {args.output}")
    for prefix, count in per_prefix_counts.items():
        print(f"  {prefix}: {count}")


if __name__ == "__main__":
    main()

