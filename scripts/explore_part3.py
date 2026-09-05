"""
SIH26143 — Detection subsystem
Step 1 (Part III, explore-first): extract the single combined Part III
archive and report its ACTUAL folder structure and file counts, before
writing any manifest/pairing logic against it.

WHY THIS IS DIFFERENT FROM PART I/II'S SCRIPTS: Part I and Part II each
shipped as separate images/mask archive pairs, so this pipeline's scripts
could safely assume "images/ folder, masks/ folder, match by numeric id."
Part III ships as ONE combined archive
(02_Test_images_and_ground_truth.7z) covering three categories (oil,
no-oil, look-alike) — its internal layout hasn't been verified against
this codebase yet, so assuming the same images/masks split would be
guessing. This script only extracts and reports structure; it does NOT
build a manifest yet. Paste its output back before the real Part III
manifest-building script gets written, so that script is grounded in the
actual folder names instead of assumed ones.

Run this locally (same venv as the Part I/II scripts):

    python scripts/explore_part3.py

Requires: py7zr (same as before). Does not require tifffile/numpy since
this step only walks folders and counts files, no image reading yet.
"""

import sys
from pathlib import Path
from collections import Counter

try:
    import py7zr
except ImportError:
    sys.exit("Missing py7zr. Run: pip install py7zr")


# ---- CONFIG: adjust if your layout differs ----
RAW_DIR = Path("data/raw/zenodo_sentinel1/part3")
ARCHIVE = RAW_DIR / "02_Test_images_and_ground_truth.7z"
OUT_DIR = Path("data/processed/part3")
# -------------------------------------------------


def extract_if_needed():
    if not ARCHIVE.exists():
        sys.exit(f"Archive not found at {ARCHIVE} — check RAW_DIR/filename in this script.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(OUT_DIR.rglob("*"))
    if existing:
        print(f"{OUT_DIR} already has {len(existing)} entries — skipping extraction. "
              f"Delete the folder for a clean re-extract.")
        return

    print(f"Extracting {ARCHIVE} -> {OUT_DIR} ...")
    with py7zr.SevenZipFile(ARCHIVE, mode="r") as archive:
        names = archive.getnames()
        print(f"Archive contains {len(names)} entries.")
        archive.extractall(path=OUT_DIR)
    print("Extraction done.")


def report_structure():
    print("\n=== Folder tree (dirs only, up to 4 levels deep) ===")
    for p in sorted(OUT_DIR.rglob("*")):
        if p.is_dir():
            depth = len(p.relative_to(OUT_DIR).parts)
            if depth <= 4:
                file_count = sum(1 for f in p.iterdir() if f.is_file())
                print(f"{'  ' * depth}{p.name}/  ({file_count} files directly inside)")

    print("\n=== File extension counts, per top-level folder ===")
    top_level_dirs = [p for p in OUT_DIR.iterdir() if p.is_dir()]
    for d in sorted(top_level_dirs):
        ext_counts = Counter(f.suffix.lower() for f in d.rglob("*") if f.is_file())
        print(f"{d.name}/: {dict(ext_counts)}")

    print("\n=== Sample filenames (first 5) per leaf folder that contains files ===")
    for p in sorted(OUT_DIR.rglob("*")):
        if p.is_dir():
            files = sorted(f.name for f in p.iterdir() if f.is_file())
            if files:
                print(f"{p.relative_to(OUT_DIR)}: {files[:5]}{' ...' if len(files) > 5 else ''}")

    print("\n>>> Paste this entire output back before we write the Part III manifest/pairing script. <<<")


def main():
    extract_if_needed()
    report_structure()


if __name__ == "__main__":
    main()
