"""
SIH26143 — Detection subsystem
whole_scene_dataset.py — implements the segmentation input pipeline the
dataset's own authors (Trujillo-Acatitla et al., 2024) actually used, as
a clean alternative to sar_dataset.py's tile-based approach.

METHODOLOGY DIFFERENCE FROM sar_dataset.py, confirmed from the paper text
(Marine Pollution Bulletin 204 (2024) 116549):
  "Each image was then divided into 2048 x 2048 pixel size sub-images for
  both polarizations (VV, VH) ... To optimize the computational cost, the
  sub-images were resized to 512 x 512 for both channels (VV, VH)."

That's a whole-scene DOWNSAMPLE, not a tiled crop. sar_dataset.py's
SARTileDataset instead extracts ~25 overlapping 512x512 CROPS per
2048x2048 scene (stride 384) — each crop sees full resolution but zero
scene-level context, and most crops of an oil-positive scene still
contain no oil at all (spills don't fill the frame). The whole-scene
resize sees the ENTIRE spill's shape/elongation/context in one shot, at
the cost of ~4x coarser per-pixel resolution (each output pixel covers a
4x4 block of source pixels). This is very likely a meaningful part of why
the paper's U-Net reached IoU in the 90s while a tile-based approach
plateaus much lower on the same source data — shape/context is one of
the strongest signals separating real oil (elongated, wind-streaked) from
look-alikes (blobby, diffuse), and tiling throws exactly that away.

This is NOT a strict replacement for sar_dataset.py — both are legitimate
and worth A/B testing against each other (see project doc §7). Fine
boundary detail is a real advantage of the tile approach; scene-level
context is a real advantage of this one. Recommended first experiment:
this whole-scene approach, oil-only manifest (via
build_oil_only_manifest.py), Focal Loss, from-scratch encoder (matching
the paper as closely as possible) as the reference point to beat.

Uses percentile_normalize/lee_filter from sar_dataset.py directly — same
normalization convention, so a checkpoint's expected input distribution
stays consistent whether you're comparing tile-trained vs scene-trained
runs.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

import cv2
import numpy as np
import tifffile
import torch
from torch.utils.data import Dataset

from sar_dataset import lee_filter, percentile_normalize

SCENE_OUTPUT_SIZE = 512  # matches the paper's reported resize target


def load_wholescene_manifest(manifest_csv: str | Path) -> list[dict]:
    manifest_csv = Path(manifest_csv)
    with open(manifest_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if not Path(r["image_path"]).exists():
            raise FileNotFoundError(f"image_path does not exist: {r['image_path']} (id={r['id']})")
        if not Path(r["mask_path"]).exists():
            raise FileNotFoundError(f"mask_path does not exist: {r['mask_path']} (id={r['id']})")
    return rows


class SARWholeSceneDataset(Dataset):
    """Yields (image, mask) as torch tensors, CHW format, both resized to
    SCENE_OUTPUT_SIZE x SCENE_OUTPUT_SIZE from the native 2048x2048 scene.

    image: float32, shape (2, 512, 512), values in [0, 1] (post percentile-normalize)
    mask:  float32, shape (1, 512, 512), values in [0, 1] (soft — see note below)

    RESIZE INTERPOLATION CHOICE MATTERS:
    - Image channels (continuous dB-derived values): cv2.INTER_AREA, the
      correct choice for shrinking — it's a local-averaging resize, unlike
      INTER_LINEAR/INTER_CUBIC which can alias/ring on a 4x downsample.
    - Mask (binary {0,1}): INTER_AREA is used here too, DELIBERATELY, and
      the result is NOT re-thresholded back to hard {0,1}. Downsampling a
      binary mask 4x means a single output pixel can genuinely be
      "37% oil" if the source 4x4 block was partially covered by the
      spill boundary — INTER_NEAREST would instead pick one arbitrary
      source pixel per block and silently discard sub-pixel boundary
      information, which measurably hurts a Dice/IoU-style loss right
      where it matters most (the boundary). Loss functions here work fine
      with soft targets in [0,1] (BCE and Dice both accept them
      naturally). If you need hard masks for a metric computation,
      threshold AFTER resizing, not before.
    """

    def __init__(self, rows: list[dict], augment: bool = False, despeckle: bool = False):
        self.rows = rows
        self.augment = augment
        self.despeckle = despeckle

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int):
        row = self.rows[idx]
        image = tifffile.imread(row["image_path"])  # (2048, 2048, 2) float32, dB
        mask = tifffile.imread(row["mask_path"]).astype(np.float32)  # (2048, 2048)

        if self.despeckle:
            # Must happen before normalize AND before resize — lee_filter
            # needs the real dB values in their native resolution to
            # estimate local speckle statistics correctly; resizing first
            # would blur the very noise texture the filter is meant to
            # characterize.
            image = lee_filter(image)

        image = percentile_normalize(image)  # -> [0,1], still (2048,2048,2)

        image_small = cv2.resize(image, (SCENE_OUTPUT_SIZE, SCENE_OUTPUT_SIZE), interpolation=cv2.INTER_AREA)
        mask_small = cv2.resize(mask, (SCENE_OUTPUT_SIZE, SCENE_OUTPUT_SIZE), interpolation=cv2.INTER_AREA)

        if image_small.ndim == 2:  # cv2 can squeeze a (H,W,1) to (H,W) — guard against it
            image_small = image_small[:, :, None]

        if self.augment:
            if random.random() < 0.5:
                image_small = np.flip(image_small, axis=0)
                mask_small = np.flip(mask_small, axis=0)
            if random.random() < 0.5:
                image_small = np.flip(image_small, axis=1)
                mask_small = np.flip(mask_small, axis=1)
            k = random.randint(0, 3)
            if k:
                image_small = np.rot90(image_small, k=k, axes=(0, 1))
                mask_small = np.rot90(mask_small, k=k, axes=(0, 1))
            # Deliberately no brightness/contrast jitter — same reasoning
            # as sar_dataset.py: physically meaningless on dB-scale radar
            # backscatter, not an oversight.

        image_small = np.transpose(image_small, (2, 0, 1)).copy()  # HWC -> CHW
        mask_small = mask_small[None, :, :].copy()  # HW -> CHW (1 channel)

        return torch.from_numpy(image_small).float(), torch.from_numpy(mask_small).float()
