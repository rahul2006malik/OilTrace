"""
SIH26143 — Detection subsystem
Step 1 (Part II): extract the Lookalike and No-Oil archives, build a
matched, collision-safe manifest, and verify the core assumption Part II
exists to provide: every mask must be genuinely all-zero.

DIFFERENCES FROM extract_and_inspect_part1.py (don't reuse that script
as-is for Part II — these are real, not cosmetic, differences):

  1. Part II is TWO separate archive pairs (Lookalike, No_Oil), each with
     its own images/mask archive. Their internal numeric filenames very
     likely overlap (both probably start at 1.tif) — extracting both into
     one shared folder and matching by numeric ID the way Part I's script
     does would silently pair a Lookalike image with a No_Oil mask (or
     just overwrite files with the same name). This script extracts each
     subset into its OWN subfolder and prefixes every id with its subset
     name (lookalike_/nooil_) so ids can never collide with each other —
     or with Part I's plain numeric ids, once you merge manifests later.

  2. Part I's script never checked mask content — Part I masks are
     SUPPOSED to have real oil pixels, so "found a matching pair" was
     enough. Part II's entire purpose is negative examples: every mask
     here MUST be all-zero. This script checks that for every single
     mask (not just a sample), and reports counts, because a single
     accidentally-non-zero mask in your negative set would poison
     val_false_positive_rate and add_lookalikes_as_negatives() silently.

Run this locally (same venv as Part I's script):

    python scripts/extract_and_inspect_part2.py

Requires: py7zr, tifffile, numpy (same as Part I's script).
"""

import re
import sys
import json
from pathlib import Path

import numpy as np

try:
    import py7zr
except ImportError:
    sys.exit("Missing py7zr. Run: pip install py7zr")

try:
    import tifffile
except ImportError:
    sys.exit("Missing tifffile. Run: pip install tifffile")


# ---- CONFIG: adjust these if your layout differs ----
RAW_DIR = Path("data/raw/zenodo_sentinel1/part2")

SUBSETS = {
    "lookalike": {
        "images_archive": RAW_DIR / "01_Train_Val_Lookalike_images.7z",
        "masks_archive": RAW_DIR / "01_Train_Val_Lookalike_mask.7z",
        "expected_count": 685,
    },
    "nooil": {
        "images_archive": RAW_DIR / "01_Train_Val_No_Oil_Images.7z",
        "masks_archive": RAW_DIR / "01_Train_Val_No_Oil_mask.7z",
        "expected_count": 685,
    },
}

OUT_DIR = Path("data/processed/part2")
MANIFEST_PATH = OUT_DIR / "manifest_part2.csv"
INSPECTION_PATH = OUT_DIR / "inspection_report_part2.json"
# -------------------------------------------------------

ID_PATTERN = re.compile(r"(\d+)\.tif$", re.IGNORECASE)


def extract_archive(archive_path: Path, dest_dir: Path, label: str):
    if not archive_path.exists():
        sys.exit(f"[{label}] Archive not found at {archive_path} — check RAW_DIR/filenames in this script.")

    dest_dir.mkdir(parents=True, exist_ok=True)

    existing = list(dest_dir.rglob("*.tif"))
    if existing:
        print(f"[{label}] {dest_dir} already has {len(existing)} .tif files (recursive) — skipping extraction. "
              f"Delete the folder if you want a clean re-extract.")
        return

    print(f"[{label}] Extracting {archive_path} -> {dest_dir} ...")
    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        names = archive.getnames()
        print(f"[{label}] Archive contains {len(names)} entries.")
        archive.extractall(path=dest_dir)
    # Same reasoning as Part I's script: don't flatten/move right after
    # extractall() on Windows — py7zr's background write threads can still
    # hold file handles, causing a PermissionError on an immediate move.
    # Just search recursively (rglob) instead.

    extracted = list(dest_dir.rglob("*.tif"))
    print(f"[{label}] Done. {len(extracted)} .tif files found under {dest_dir} (recursive).")


def extract_numeric_id(filename: str) -> str | None:
    m = ID_PATTERN.search(filename)
    return m.group(1) if m else None


def build_subset_manifest(subset_name: str, cfg: dict):
    subset_dir = OUT_DIR / subset_name
    images_dir = subset_dir / "images"
    masks_dir = subset_dir / "masks"

    extract_archive(cfg["images_archive"], images_dir, f"{subset_name}-images")
    extract_archive(cfg["masks_archive"], masks_dir, f"{subset_name}-masks")

    image_files = {extract_numeric_id(p.name): p for p in images_dir.rglob("*.tif")}
    mask_files = {extract_numeric_id(p.name): p for p in masks_dir.rglob("*.tif")}

    image_ids = set(k for k in image_files if k is not None)
    mask_ids = set(k for k in mask_files if k is not None)
    matched = sorted(image_ids & mask_ids, key=int)

    print(f"\n--- {subset_name}: manifest summary ---")
    print(f"Images found:  {len(image_ids)}")
    print(f"Masks found:   {len(mask_ids)}")
    print(f"Matched pairs: {len(matched)}")
    unmatched_imgs = sorted(image_ids - mask_ids, key=int)
    unmatched_masks = sorted(mask_ids - image_ids, key=int)
    if unmatched_imgs:
        print(f"Images with NO mask: {len(unmatched_imgs)}  e.g. {unmatched_imgs[:10]}")
    if unmatched_masks:
        print(f"Masks with NO image: {len(unmatched_masks)}  e.g. {unmatched_masks[:10]}")

    expected = cfg["expected_count"]
    if len(matched) != expected:
        print(f"*** WARNING: expected {expected} matched pairs for '{subset_name}' per the Zenodo docs, "
              f"got {len(matched)}. Don't proceed assuming the full count until you know why. ***")

    # Verify EVERY mask in this subset is genuinely all-zero — this is the
    # one property Part II exists to guarantee. Report counts, don't just
    # spot-check, and don't silently drop violators — surface them.
    non_zero_masks = []
    for local_id in matched:
        mask = tifffile.imread(mask_files[local_id])
        if np.any(mask != 0):
            non_zero_masks.append((local_id, str(mask_files[local_id]), int(np.count_nonzero(mask))))

    if non_zero_masks:
        print(f"*** WARNING: {len(non_zero_masks)}/{len(matched)} masks in '{subset_name}' are NOT all-zero. "
              f"These are not safe to treat as pure negatives — examples: {non_zero_masks[:5]} ***")
    else:
        print(f"Verified: all {len(matched)} masks in '{subset_name}' are genuinely all-zero.")

    # Prefix every id with the subset name so it can never collide with the
    # other subset, or with Part I's plain numeric ids, once manifests get
    # merged downstream.
    rows = []
    non_zero_ids = {nid for nid, _, _ in non_zero_masks}
    for local_id in matched:
        global_id = f"{subset_name}_{local_id}"
        is_clean_negative = local_id not in non_zero_ids
        rows.append({
            "id": global_id,
            "image_path": str(image_files[local_id]),
            "mask_path": str(mask_files[local_id]),
            "subset": subset_name,
            "verified_all_zero_mask": is_clean_negative,
        })

    return rows, non_zero_masks


def inspect_one_pair(subset_name: str, row: dict):
    img = tifffile.imread(row["image_path"])
    mask = tifffile.imread(row["mask_path"])

    report = {
        "subset": subset_name,
        "sample_id": row["id"],
        "image_path": row["image_path"],
        "mask_path": row["mask_path"],
        "image_shape": list(img.shape),
        "image_dtype": str(img.dtype),
        "image_min": float(np.nanmin(img)),
        "image_max": float(np.nanmax(img)),
        "mask_shape": list(mask.shape),
        "mask_dtype": str(mask.dtype),
        "mask_unique_values": [float(v) for v in np.unique(mask)[:20]],
    }
    print(f"\n--- Sample inspection: {subset_name} ---")
    print(json.dumps(report, indent=2))
    return report


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []
    all_non_zero = {}
    inspections = []

    for subset_name, cfg in SUBSETS.items():
        rows, non_zero_masks = build_subset_manifest(subset_name, cfg)
        all_rows.extend(rows)
        all_non_zero[subset_name] = non_zero_masks
        if rows:
            inspections.append(inspect_one_pair(subset_name, rows[0]))

    if not all_rows:
        sys.exit("No matched pairs found across either subset — stopping before writing a manifest.")

    with open(MANIFEST_PATH, "w") as f:
        f.write("id,image_path,mask_path,subset,verified_all_zero_mask\n")
        for r in all_rows:
            f.write(f"{r['id']},{r['image_path']},{r['mask_path']},{r['subset']},{r['verified_all_zero_mask']}\n")

    total_non_zero = sum(len(v) for v in all_non_zero.values())
    print(f"\n=== Part II combined manifest: {len(all_rows)} total rows written to {MANIFEST_PATH} ===")
    if total_non_zero:
        print(f"*** {total_non_zero} rows are flagged verified_all_zero_mask=False. Filter these out "
              f"(or investigate them) before treating this manifest as pure hard negatives. ***")
    else:
        print("All masks across both subsets verified all-zero. Safe to use as pure negatives.")

    with open(INSPECTION_PATH, "w") as f:
        json.dump({"inspections": inspections, "non_zero_mask_counts": {k: len(v) for k, v in all_non_zero.items()}}, f, indent=2)
    print(f"Inspection report written to {INSPECTION_PATH}")
    print("\n>>> Paste the manifest summary + inspection JSON back here before we upload Part II to Kaggle. <<<")


if __name__ == "__main__":
    main()
