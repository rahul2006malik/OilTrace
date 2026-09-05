#!/usr/bin/env python3
"""
SIH26143 / OilTrace — Resumable, checksum-verified Zenodo Sentinel-1 downloader (pure Python).

Covers all 3 parts of: Trujillo-Acatitla et al., "Sentinel-1 SAR Oil spill image
dataset for train, validate, and test deep learning models" (Parts I-III, Zenodo,
CC-BY-4.0). URLs and MD5s pulled live from the Zenodo records on 27 Aug 2026.

Requirements:
    pip install requests

Usage:
    python download_zenodo_sentinel1.py                # everything (~96.5 GB)
    python download_zenodo_sentinel1.py part1           # Part I only (~40.7 GB, oil spill)
    python download_zenodo_sentinel1.py part2           # Part II only (~45.9 GB, no-oil + lookalike)
    python download_zenodo_sentinel1.py part3           # Part III only (~9.9 GB, test set)

Safe to re-run any time, on any OS (Windows/Mac/Linux): if a file was interrupted
partway, this resumes from the exact byte it stopped at using HTTP range requests
(the server-side equivalent of wget -c). Files that already passed MD5 verification
are skipped entirely on the next run. Corrupt/mismatched files are deleted and
retried automatically. Does NOT extract the .7z archives.
"""

import argparse
import hashlib
import os
import shutil
import sys
import time

import requests

CHUNK_SIZE = 1024 * 1024  # 1 MB
MAX_ATTEMPTS = 6

# name, url, md5, subdir
FILES = [
    ("01_Train_Val_Oil_Spill_images.7z",
     "https://zenodo.org/records/8346860/files/01_Train_Val_Oil_Spill_images.7z?download=1",
     "e2a6a5b473ca587474d8daee9cd54e10", "part1"),
    ("01_Train_Val_Oil_Spill_mask.7z",
     "https://zenodo.org/records/8346860/files/01_Train_Val_Oil_Spill_mask.7z?download=1",
     "9bc53c38db2ab82d15bf6914352403ef", "part1"),
    ("01_Train_Val_Lookalike_images.7z",
     "https://zenodo.org/records/8253899/files/01_Train_Val_Lookalike_images.7z?download=1",
     "e0af26e0b2ad7979b889a91ed5df9a41", "part2"),
    ("01_Train_Val_Lookalike_mask.7z",
     "https://zenodo.org/records/8253899/files/01_Train_Val_Lookalike_mask.7z?download=1",
     "ed7370a3dac9fff9287b5254349fdc26", "part2"),
    ("01_Train_Val_No_Oil_Images.7z",
     "https://zenodo.org/records/8253899/files/01_Train_Val_No_Oil_Images.7z?download=1",
     "6836df2bea59ebb73479ffea71828e14", "part2"),
    ("01_Train_Val_No_Oil_mask.7z",
     "https://zenodo.org/records/8253899/files/01_Train_Val_No_Oil_mask.7z?download=1",
     "1b152ee4dd93173015197d0a82b2c864", "part2"),
    ("02_Test_images_and_ground_truth.7z",
     "https://zenodo.org/records/13761290/files/02_Test_images_and_ground_truth.7z?download=1",
     "5dce64cd7ff9d80189d13504bd3bcbf5", "part3"),
]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def verify_md5(path: str, expected_md5: str) -> bool:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest() == expected_md5


def print_progress(downloaded: int, total: int, start_time: float) -> None:
    if total <= 0:
        return
    pct = downloaded / total * 100
    elapsed = max(time.time() - start_time, 0.001)
    speed_mb_s = downloaded / elapsed / (1024 * 1024)
    bar_len = 30
    filled = int(bar_len * pct / 100)
    bar = "#" * filled + "-" * (bar_len - filled)
    sys.stdout.write(
        f"\r  [{bar}] {pct:5.1f}%  {human(downloaded)}/{human(total)}  {speed_mb_s:5.1f} MB/s"
    )
    sys.stdout.flush()


def get_remote_size(url: str, session: requests.Session) -> int:
    r = session.head(url, allow_redirects=True, timeout=30)
    r.raise_for_status()
    return int(r.headers.get("Content-Length", 0))


def download_file(name: str, url: str, md5: str, subdir: str, base_dir: str,
                   session: requests.Session) -> bool:
    dest_dir = os.path.join(base_dir, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)

    print(f"\n=== {name} ({subdir}) ===")

    if os.path.exists(dest) and verify_md5(dest, md5):
        print("  Already downloaded and MD5-verified — skipping.")
        return True

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            remote_size = get_remote_size(url, session)
        except Exception as e:
            print(f"  Could not reach server (attempt {attempt}/{MAX_ATTEMPTS}): {e}")
            time.sleep(5 * attempt)
            continue

        free_space = shutil.disk_usage(dest_dir).free
        if free_space < remote_size:
            print(f"  NOT ENOUGH DISK SPACE: {human(free_space)} free, "
                  f"file is {human(remote_size)}. Free up space and re-run this script.")
            return False

        existing = os.path.getsize(dest) if os.path.exists(dest) else 0
        mode = "wb"
        headers = {}
        if 0 < existing < remote_size:
            headers["Range"] = f"bytes={existing}-"
            mode = "ab"
            print(f"  Resuming from {human(existing)} / {human(remote_size)}")
        else:
            if existing >= remote_size and remote_size > 0:
                existing = 0  # stale/complete-but-unverified file, restart clean
            print(f"  Starting download — {human(remote_size)}")

        try:
            with session.get(url, headers=headers, stream=True, timeout=60) as r:
                if headers and r.status_code == 200:
                    print("  Server doesn't support resuming this file — restarting from 0.")
                    mode, existing = "wb", 0
                elif r.status_code not in (200, 206):
                    r.raise_for_status()

                downloaded = existing
                start_time = time.time()
                with open(dest, mode) as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        print_progress(downloaded, remote_size, start_time)
            print()
        except (requests.exceptions.RequestException, ConnectionError, OSError) as e:
            print(f"\n  Download interrupted (attempt {attempt}/{MAX_ATTEMPTS}): {e}")
            print("  (Partial file kept — next attempt resumes from here.)")
            time.sleep(5 * attempt)
            continue

        print("  Verifying MD5 (reads the whole file once)...")
        if verify_md5(dest, md5):
            print(f"  MD5 OK for {name}.")
            return True
        else:
            print(f"  MD5 MISMATCH for {name} — deleting and retrying from scratch.")
            os.remove(dest)
            time.sleep(5)

    print(f"  FAILED: {name} could not be downloaded/verified after {MAX_ATTEMPTS} attempts.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the Zenodo Sentinel-1 oil spill dataset.")
    parser.add_argument("part", nargs="?", default="all", choices=["all", "part1", "part2", "part3"])
    parser.add_argument("--base-dir", default="data/raw/zenodo_sentinel1")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "OilTrace-SIH26143-downloader/1.0"})

    failed = []
    for name, url, md5, subdir in FILES:
        if args.part != "all" and args.part != subdir:
            continue
        if not download_file(name, url, md5, subdir, args.base_dir, session):
            failed.append(name)

    print("\n" + "=" * 60)
    if not failed:
        print("All requested archives downloaded and MD5-verified successfully.")
        print(f"Layout: {args.base_dir}/part1  {args.base_dir}/part2  {args.base_dir}/part3")
        print("(Archives were NOT extracted.)")
    else:
        print("Incomplete/failed files:")
        for name in failed:
            print(f"  - {name}")
        print("Just re-run the exact same command — completed files are skipped automatically.")


if __name__ == "__main__":
    main()
