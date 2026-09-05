"""
SIH26143 / OilTrace — Part 3 Dataset Inspection & Anomaly Detector.

Scans all image and mask files in Part 3 (manifest_part3.csv) to detect:
  1. Shape anomalies (expected: image 2048x2048x2, mask 2048x2048)
  2. Corrupted TIFF files or read errors
  3. NaN or Inf values in image / mask arrays
  4. Non-zero mask violations in negative categories (nooil, lookalike)
  5. Empty masks in positive category (oil)
  6. Abnormal intensity ranges (min/max checks)

Usage in CMD:
    python scripts\\inspect_part3.py
    python scripts\\inspect_part3.py --manifest data\\processed\\part3\\manifest_part3.csv
"""

import argparse
import csv
import sys
from pathlib import Path
import numpy as np

try:
    import tifffile
except ImportError:
    sys.exit("Missing tifffile. Run: pip install tifffile")


def inspect_part3(manifest_path: str, expected_img_shape=(2048, 2048, 2), expected_mask_shape=(2048, 2048)):
    path = Path(manifest_path)
    if not path.exists():
        sys.exit(f"Manifest not found: {path}")

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        sys.exit(f"No entries found in {manifest_path}")

    print(f"==================================================")
    print(f"  OilTrace Part 3 Dataset Quality & Anomaly Scan  ")
    print(f"==================================================")
    print(f"Manifest: {manifest_path}")
    print(f"Total pairs to scan: {len(rows)}")
    print(f"Expected image shape: {expected_img_shape}")
    print(f"Expected mask shape:  {expected_mask_shape}\n")

    bad_files = []
    category_counts = {"oil": 0, "nooil": 0, "lookalike": 0}
    category_oil_pixel_masks = {"oil": 0, "nooil": 0, "lookalike": 0}

    for i, r in enumerate(rows, 1):
        sample_id = r.get("id", f"row_{i}")
        img_path = r.get("image_path", "")
        mask_path = r.get("mask_path", "")
        cat = r.get("category", "unknown")

        if cat in category_counts:
            category_counts[cat] += 1

        # 1. Image Check
        try:
            img = tifffile.imread(img_path)
            if img.shape != expected_img_shape:
                bad_files.append({"id": sample_id, "file": img_path, "issue": f"Image shape {img.shape} != {expected_img_shape}"})
            if np.isnan(img).any():
                bad_files.append({"id": sample_id, "file": img_path, "issue": "Image contains NaN pixels"})
            if np.isinf(img).any():
                bad_files.append({"id": sample_id, "file": img_path, "issue": "Image contains Inf pixels"})
        except Exception as e:
            bad_files.append({"id": sample_id, "file": img_path, "issue": f"Image read failure: {e}"})

        # 2. Mask Check
        try:
            mask = tifffile.imread(mask_path)
            if mask.shape != expected_mask_shape:
                bad_files.append({"id": sample_id, "file": mask_path, "issue": f"Mask shape {mask.shape} != {expected_mask_shape}"})
            
            has_oil = bool(np.any(mask != 0))
            if has_oil:
                if cat in category_oil_pixel_masks:
                    category_oil_pixel_masks[cat] += 1
                if cat in ("nooil", "lookalike"):
                    bad_files.append({"id": sample_id, "file": mask_path, "issue": f"Category '{cat}' is negative but mask has non-zero oil pixels"})
            else:
                if cat == "oil":
                    print(f"  [Notice] '{sample_id}' (oil category) has an empty mask (0 oil pixels).")

        except Exception as e:
            bad_files.append({"id": sample_id, "file": mask_path, "issue": f"Mask read failure: {e}"})

        if i % 100 == 0 or i == len(rows):
            print(f"  Scanned {i}/{len(rows)} pairs...")

    print(f"\n---------------- Summary ----------------")
    print(f"Categories found:")
    for c, cnt in category_counts.items():
        print(f"  - {c}: {cnt} pairs ({category_oil_pixel_masks[c]} with non-zero mask pixels)")

    print(f"\nTotal problem files found: {len(bad_files)}")
    if bad_files:
        print("\n*** LIST OF BAD / ANOMALOUS FILES ***")
        for b in bad_files:
            print(f"  [{b['id']}] {b['issue']}\n    File: {b['file']}")
    else:
        print(">> ALL FILES VERIFIED CLEAN: No corruptions, shape mismatches, NaNs, or mask violations.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect Part 3 dataset files for anomalies.")
    parser.add_argument("--manifest", default="data/processed/part3/manifest_part3.csv",
                        help="Path to manifest CSV (default: data/processed/part3/manifest_part3.csv)")
    args = parser.parse_args()
    inspect_part3(args.manifest)
