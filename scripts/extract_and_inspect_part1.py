"""
SIH26143 — Detection subsystem
Step 1: extract Part I archives, build a matched image/mask manifest, and
inspect one real file so we stop guessing about band count / dtype.

Run this locally (Windows, your venv with py7zr already installed):

    python scripts/extract_and_inspect_part1.py

Requires: py7zr, tifffile, numpy  (tifffile handles multi-band SAR TIFFs far
more reliably than PIL for this dataset family — PIL silently mishandles
16-bit / multi-page TIFFs in ways that are easy to miss).

    pip install py7zr tifffile numpy

Does NOT require GPU packages — this step is pure I/O + inspection.
"""

import re
import sys
import json
import shutil
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


# ---- CONFIG: adjust these two paths if your layout differs ----
RAW_DIR = Path("data/raw/zenodo_sentinel1/part1")
IMAGES_ARCHIVE = RAW_DIR / "01_Train_Val_Oil_Spill_images.7z"
MASKS_ARCHIVE = RAW_DIR / "01_Train_Val_Oil_Spill_mask.7z"

OUT_DIR = Path("data/processed/part1")
OUT_IMAGES = OUT_DIR / "images"
OUT_MASKS = OUT_DIR / "masks"
MANIFEST_PATH = OUT_DIR / "manifest_part1.csv"
INSPECTION_PATH = OUT_DIR / "inspection_report.json"
# -----------------------------------------------------------------

ID_PATTERN = re.compile(r"(\d+)\.tif$", re.IGNORECASE)


def extract_archive(archive_path: Path, dest_dir: Path, label: str):
    if not archive_path.exists():
        sys.exit(f"[{label}] Archive not found at {archive_path} — check RAW_DIR/filenames in this script.")

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Skip re-extraction if it looks like it already ran (recursive check,
    # since we no longer flatten — files stay under their archive subfolder).
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
    # NOTE: deliberately not flattening subfolders (Oil/, Mask_oil/) here.
    # py7zr on Windows can return from extractall() before background write
    # threads release file handles, so an immediate shutil.move() right after
    # can hit a PermissionError on a still-locked file. Simplest robust fix:
    # don't move anything — just search recursively (rglob) everywhere below.

    extracted = list(dest_dir.rglob("*.tif"))
    print(f"[{label}] Done. {len(extracted)} .tif files found under {dest_dir} (recursive).")


def extract_id(filename: str) -> str | None:
    m = ID_PATTERN.search(filename)
    return m.group(1) if m else None


def build_manifest():
    image_files = {extract_id(p.name): p for p in OUT_IMAGES.rglob("*.tif")}
    mask_files = {extract_id(p.name): p for p in OUT_MASKS.rglob("*.tif")}

    image_ids = set(k for k in image_files if k is not None)
    mask_ids = set(k for k in mask_files if k is not None)

    matched = sorted(image_ids & mask_ids, key=int)
    images_without_mask = sorted(image_ids - mask_ids, key=int)
    masks_without_image = sorted(mask_ids - image_ids, key=int)

    print(f"\n--- Manifest summary ---")
    print(f"Images found:            {len(image_ids)}")
    print(f"Masks found:             {len(mask_ids)}")
    print(f"Matched pairs:           {len(matched)}")
    print(f"Images with NO mask:     {len(images_without_mask)}"
          + (f"  e.g. {images_without_mask[:10]}" if images_without_mask else ""))
    print(f"Masks with NO image:     {len(masks_without_image)}"
          + (f"  e.g. {masks_without_image[:10]}" if masks_without_image else ""))

    if len(matched) != 1200:
        print(f"\n*** WARNING: expected 1200 matched pairs for Part I per the Zenodo dataset docs, "
              f"got {len(matched)}. This could mean: (a) the docs are wrong, (b) your download is "
              f"incomplete despite MD5 passing on the archives themselves, or (c) some images "
              f"legitimately have no annotated mask. Don't proceed to training assuming 1200 until "
              f"you know which. ***\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        f.write("id,image_path,mask_path\n")
        for i in matched:
            f.write(f"{i},{image_files[i]},{mask_files[i]}\n")
    print(f"Manifest written to {MANIFEST_PATH}")

    return matched, image_files, mask_files


def inspect_one_pair(sample_id: str, image_files: dict, mask_files: dict):
    img_path = image_files[sample_id]
    mask_path = mask_files[sample_id]

    img = tifffile.imread(img_path)
    mask = tifffile.imread(mask_path)

    report = {
        "sample_id": sample_id,
        "image_path": str(img_path),
        "mask_path": str(mask_path),
        "image_shape": list(img.shape),
        "image_dtype": str(img.dtype),
        "image_min": float(np.nanmin(img)),
        "image_max": float(np.nanmax(img)),
        "image_has_nan": bool(np.isnan(img).any()) if np.issubdtype(img.dtype, np.floating) else False,
        "mask_shape": list(mask.shape),
        "mask_dtype": str(mask.dtype),
        "mask_unique_values": [float(v) for v in np.unique(mask)[:20]],
    }

    print("\n--- Sample file inspection ---")
    print(json.dumps(report, indent=2))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(INSPECTION_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nInspection report written to {INSPECTION_PATH}")
    print("\n>>> Paste the JSON above back into the Detection thread before we write the tiling/normalization code. <<<")


def main():
    extract_archive(IMAGES_ARCHIVE, OUT_IMAGES, "images")
    extract_archive(MASKS_ARCHIVE, OUT_MASKS, "masks")

    matched, image_files, mask_files = build_manifest()

    if not matched:
        sys.exit("No matched pairs found — stopping before inspection. Check the extraction output above.")

    inspect_one_pair(matched[0], image_files, mask_files)


if __name__ == "__main__":
    main()