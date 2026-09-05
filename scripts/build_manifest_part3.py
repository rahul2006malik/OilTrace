"""
SIH26143 — Detection subsystem
Step 2 (Part III): build the manifest for the held-out test set, now that
explore_part3.py has confirmed the real layout:

    data/processed/part3/Images/{Oil, No oil, Lookalike}/NNNNN.tif
    data/processed/part3/Mask/{Oil, No oil, Lookalike}/NNNNN_segmentation.tif

Pairs each category by numeric id, verifies the same core assumption as
Part II for the No-oil and Lookalike categories (masks must be genuinely
all-zero), and reports basic stats for the Oil category (should have real
oil pixels in most/all masks — this is the positive class Part III is
scored against).

Writes ONE combined manifest (id,image_path,mask_path,category) with the
same id/image_path/mask_path columns evaluate_part3.py already expects —
category is an extra column DictReader will simply ignore there.

Global ids are prefixed test_<category>_<numeric-id> so they can never
collide with Part I's plain numeric ids or Part II's lookalike_/nooil_
prefixed ids, in case manifests ever get concatenated by mistake. THIS
MANIFEST SHOULD NEVER ACTUALLY BE MERGED WITH THE TRAINING MANIFEST —
Part III stays held out. The prefix is a safety net, not permission.

Run this locally, after explore_part3.py has already extracted the data:

    python scripts/build_manifest_part3.py

Requires: tifffile, numpy (same as the Part I/II scripts).
"""

import re
import sys
import json
from pathlib import Path

import numpy as np

try:
    import tifffile
except ImportError:
    sys.exit("Missing tifffile. Run: pip install tifffile")


OUT_DIR = Path("data/processed/part3")
IMAGES_ROOT = OUT_DIR / "Images"
MASKS_ROOT = OUT_DIR / "Mask"
MANIFEST_PATH = OUT_DIR / "manifest_part3.csv"
INSPECTION_PATH = OUT_DIR / "inspection_report_part3.json"

# Maps the real on-disk folder name -> a clean id-safe category key.
CATEGORIES = {
    "Oil": "oil",
    "No oil": "nooil",
    "Lookalike": "lookalike",
}
EXPECTED_COUNT_PER_CATEGORY = 150

ID_PATTERN = re.compile(r"(\d+)\.tif$", re.IGNORECASE)
MASK_ID_PATTERN = re.compile(r"(\d+)_segmentation\.tif$", re.IGNORECASE)


def build_category_manifest(folder_name: str, category_key: str):
    images_dir = IMAGES_ROOT / folder_name
    masks_dir = MASKS_ROOT / folder_name

    if not images_dir.exists() or not masks_dir.exists():
        sys.exit(f"Expected folders not found: {images_dir} / {masks_dir}. "
                  f"Did explore_part3.py's extraction actually finish? Check the folder name matches exactly "
                  f"(note the space in 'No oil').")

    image_files = {}
    for p in images_dir.glob("*.tif"):
        m = ID_PATTERN.search(p.name)
        if m:
            image_files[m.group(1)] = p

    mask_files = {}
    for p in masks_dir.glob("*.tif"):
        m = MASK_ID_PATTERN.search(p.name)
        if m:
            mask_files[m.group(1)] = p

    image_ids = set(image_files)
    mask_ids = set(mask_files)
    matched = sorted(image_ids & mask_ids, key=int)

    print(f"\n--- {category_key}: manifest summary ---")
    print(f"Images found:  {len(image_ids)}")
    print(f"Masks found:   {len(mask_ids)}")
    print(f"Matched pairs: {len(matched)}")
    unmatched_imgs = sorted(image_ids - mask_ids, key=int)
    unmatched_masks = sorted(mask_ids - image_ids, key=int)
    if unmatched_imgs:
        print(f"Images with NO mask: {len(unmatched_imgs)}  e.g. {unmatched_imgs[:10]}")
    if unmatched_masks:
        print(f"Masks with NO image: {len(unmatched_masks)}  e.g. {unmatched_masks[:10]}")

    if len(matched) != EXPECTED_COUNT_PER_CATEGORY:
        print(f"*** WARNING: expected {EXPECTED_COUNT_PER_CATEGORY} pairs for '{category_key}', "
              f"got {len(matched)}. Don't assume the full set until you know why. ***")

    # For no-oil / lookalike: verify genuinely all-zero, same as Part II.
    # For oil: just report how many masks actually contain oil pixels —
    # a few legitimately-empty masks in the oil category wouldn't be a bug
    # (some real scenes may have very little annotated slick), but a LOT
    # of empty masks here would be a red flag worth knowing before you
    # trust the final oil-IoU number.
    non_zero_count = 0
    zero_count = 0
    for local_id in matched:
        mask = tifffile.imread(mask_files[local_id])
        if np.any(mask != 0):
            non_zero_count += 1
        else:
            zero_count += 1

    if category_key in ("nooil", "lookalike"):
        if non_zero_count > 0:
            print(f"*** WARNING: {non_zero_count}/{len(matched)} masks in '{category_key}' are "
                  f"NOT all-zero — this category is supposed to be pure negative. ***")
        else:
            print(f"Verified: all {len(matched)} masks in '{category_key}' are genuinely all-zero.")
    else:  # oil
        print(f"'{category_key}': {non_zero_count}/{len(matched)} masks contain real oil pixels, "
              f"{zero_count}/{len(matched)} are empty.")
        if zero_count > len(matched) * 0.1:
            print(f"*** NOTE: more than 10% of 'oil' masks are empty — worth spot-checking a few before "
                  f"trusting the final report. ***")

    rows = []
    for local_id in matched:
        rows.append({
            "id": f"test_{category_key}_{local_id}",
            "image_path": str(image_files[local_id]),
            "mask_path": str(mask_files[local_id]),
            "category": category_key,
        })
    return rows


def inspect_one_pair(category_key: str, row: dict):
    img = tifffile.imread(row["image_path"])
    mask = tifffile.imread(row["mask_path"])
    report = {
        "category": category_key,
        "sample_id": row["id"],
        "image_shape": list(img.shape),
        "image_dtype": str(img.dtype),
        "mask_shape": list(mask.shape),
        "mask_dtype": str(mask.dtype),
        "mask_unique_values": [float(v) for v in np.unique(mask)[:20]],
    }
    print(f"\n--- Sample inspection: {category_key} ---")
    print(json.dumps(report, indent=2))
    return report


def main():
    all_rows = []
    inspections = []
    for folder_name, category_key in CATEGORIES.items():
        rows = build_category_manifest(folder_name, category_key)
        all_rows.extend(rows)
        if rows:
            inspections.append(inspect_one_pair(category_key, rows[0]))

    if not all_rows:
        sys.exit("No matched pairs found across any category — stopping before writing a manifest.")

    with open(MANIFEST_PATH, "w") as f:
        f.write("id,image_path,mask_path,category\n")
        for r in all_rows:
            f.write(f"{r['id']},{r['image_path']},{r['mask_path']},{r['category']}\n")

    print(f"\n=== Part III combined manifest: {len(all_rows)} total rows written to {MANIFEST_PATH} ===")
    print("Expected 450 total (150 oil + 150 no-oil + 150 lookalike) per the Zenodo docs.")
    print("REMINDER: this manifest is for evaluate_part3.py only, ONCE, after training is fully "
          "done. Do not merge it into your training manifest, and do not use it to pick "
          "hyperparameters or checkpoints mid-training.")

    with open(INSPECTION_PATH, "w") as f:
        json.dump({"inspections": inspections}, f, indent=2)
    print(f"Inspection report written to {INSPECTION_PATH}")


if __name__ == "__main__":
    main()
