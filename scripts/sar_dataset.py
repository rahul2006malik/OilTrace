"""
SIH26143 — Detection subsystem
Step 2: tiling + normalization pipeline, built against the CONFIRMED real
data shape from Part I:

    image: (2048, 2048, 2) float32, VV+VH in dB already (range ~[-54, 5.5])
    mask:  (2048, 2048) uint8, clean binary {0, 1}

If Part II / Part III turn out to have a different dtype/shape, don't assume
it matches — re-run extract_and_inspect_part1.py's inspection logic against
a sample from each before trusting this pipeline on them blindly.

Usage (see bottom __main__ block for a smoke test you can run locally,
CPU-only, before burning Kaggle GPU time on this):

    from sar_dataset import SARTileDataset, GroupedShuffleSampler, build_tile_index

    tile_index, scene_size = build_tile_index("data/processed/part1/manifest_part1.csv",
                                               tile_size=512, stride=384)
    ds = SARTileDataset(tile_index, augment=True, scene_size=scene_size)
    sampler = GroupedShuffleSampler(tile_index, seed=42)
    # pass sampler=sampler to DataLoader instead of shuffle=True — see
    # train_unet.py for the wiring. Call sampler.set_epoch(epoch) once per
    # epoch so the shuffle order actually changes across epochs.

PERFORMANCE NOTE (added after the first full read-through of this file):
__getitem__ used to call tifffile.imread() + percentile_normalize() on the
FULL scene on every single call, even though each call only needs one
512x512 crop of it. With stride=384 that's ~25 tiles per 2048x2048 image,
so an uncached Dataset re-reads and re-normalizes the same ~32MB scene
~25 times per epoch, per image. For ~1,080 train images that's on the
order of 800GB+ of redundant disk I/O + percentile computation every
epoch — enough to make Kaggle training silently 10-25x slower than it
needs to be, which matters a lot against a 12-hour session cap and a
shared weekly GPU quota.

Fix: _SceneCache below caches the normalized (image, mask) pair for the
last few sample_ids touched by a given worker process, and
GroupedShuffleSampler keeps a worker's consecutive tile requests
clustered by source image (shuffled at the image level, and shuffled
within each image) instead of fully random across all 30,000 tiles — so
the cache actually gets hits instead of thrashing. This is NOT perfect
under multi-worker interleaving (a small fraction of images will still
get re-read more than once per epoch depending on how batches land on
workers), but it turns a guaranteed ~25x redundancy into a small one.
Confirm the win yourself by timing an epoch before and after if you want
a real number for your report.
"""

from __future__ import annotations

import csv
import random
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile
import torch
from torch.utils.data import Dataset, Sampler

# ---- CONFIG ----
TILE_SIZE = 512
DEFAULT_STRIDE = 384          # 25% overlap at 512 tile size
PCT_LOW, PCT_HIGH = 2, 98     # percentile clip bounds, per project doc §5.3
DEFAULT_CACHE_SIZE = 4        # full scenes kept per worker process
# -----------------


@dataclass(frozen=True)
class TileRef:
    """A single tile's location, resolved lazily at __getitem__ time.

    Deliberately NOT storing pixel data here — with 1200 images x ~25 tiles
    each (see coverage math below) that would mean holding gigabytes in RAM
    for something the OS page cache / disk read handles fine on demand.
    """
    sample_id: str
    image_path: str
    mask_path: str
    row: int   # top-left row of this tile in the source 2048x2048 image
    col: int   # top-left col of this tile in the source 2048x2048 image


def _tile_starts(dim_size: int, tile_size: int, stride: int) -> list[int]:
    """Compute top-left start coordinates covering dim_size with tile_size,
    stepping by stride, guaranteeing the final tile is flush with the edge
    (no partial/padded tiles) rather than silently dropping the last strip.
    """
    if dim_size < tile_size:
        raise ValueError(
            f"dim_size={dim_size} smaller than tile_size={tile_size} — "
            f"this dataset's images are documented as 2048x2048, so this "
            f"means you're pointing at a different/corrupt file."
        )
    starts = list(range(0, dim_size - tile_size + 1, stride))
    last_flush = dim_size - tile_size
    if starts[-1] != last_flush:
        starts.append(last_flush)
    return starts


def build_tile_index(
    manifest_csv: str | Path,
    tile_size: int = TILE_SIZE,
    stride: int = DEFAULT_STRIDE,
) -> list[TileRef]:
    """Reads the manifest (id,image_path,mask_path) and expands it into a
    flat list of TileRef, one per tile position. Does NOT open any image
    files — pure arithmetic over the known 2048x2048 scene size, so this
    is fast even for the full 1200-image manifest.

    NOTE: this appends all of one image's tiles before moving to the next
    image, so the returned list is already grouped by sample_id in order.
    GroupedShuffleSampler relies on this grouping to build its per-image
    groups; val_loader (shuffle=False) also benefits from it for free.
    """
    manifest_csv = Path(manifest_csv)
    if not manifest_csv.exists():
        raise FileNotFoundError(
            f"Manifest not found at {manifest_csv} — run "
            f"extract_and_inspect_part1.py first."
        )

    tile_refs: list[TileRef] = []
    with open(manifest_csv, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError(f"Manifest at {manifest_csv} has no rows.")

    # FIX: this used to only check the FIRST image's shape and assume every
    # other image in the manifest matched it. That assumption silently
    # broke once Part II was merged in — some images have a different
    # resolution, and since row_starts/col_starts are computed once from
    # scene_size and reused for every image, a smaller image would get
    # sliced past its own bounds. numpy doesn't raise on that (it just
    # returns a truncated tile), so the failure never surfaced here — it
    # surfaced as a cryptic "Trying to resize storage that is not
    # resizable" crash deep inside a DataLoader worker, hours into a real
    # training run, when collate tried to stack that malformed tile
    # against normally-shaped ones.
    #
    # This now checks EVERY image, using tifffile.TiffFile(...).shape
    # (metadata only, no pixel decode) so checking thousands of files
    # still takes seconds, not minutes.
    first_img_path = rows[0]["image_path"]
    with tifffile.TiffFile(first_img_path) as tf:
        first_shape = tf.pages[0].shape
    if first_shape[0] != first_shape[1]:
        raise ValueError(
            f"Expected a square scene, got shape {first_shape} from "
            f"{first_img_path}. This pipeline assumes square 2048x2048 "
            f"scenes per the confirmed inspection report — stopping "
            f"rather than guessing how to handle a non-square scene."
        )
    scene_size = first_shape[0]

    print(f"Verifying all {len(rows)} image shapes match {first_shape} before building the tile index...")
    shape_anomalies = []
    for row in rows:
        with tifffile.TiffFile(row["image_path"]) as tf:
            shape = tf.pages[0].shape
        if tuple(shape) != tuple(first_shape):
            shape_anomalies.append((row["id"], row["image_path"], shape))

    if shape_anomalies:
        examples = "\n".join(
            f"    id={sid}: shape={shape}  path={path}"
            for sid, path, shape in shape_anomalies[:10]
        )
        more = f"\n    ... and {len(shape_anomalies) - 10} more" if len(shape_anomalies) > 10 else ""
        raise ValueError(
            f"Found {len(shape_anomalies)} image(s) whose shape doesn't match "
            f"the expected {first_shape}:\n{examples}{more}\n"
            f"Fix or exclude these from the manifest before training — "
            f"proceeding would silently produce malformed tiles that crash "
            f"deep inside a DataLoader worker, likely hours into a real run."
        )
    print("All image shapes verified consistent.")

    row_starts = _tile_starts(scene_size, tile_size, stride)
    col_starts = _tile_starts(scene_size, tile_size, stride)

    for row in rows:
        for r in row_starts:
            for c in col_starts:
                tile_refs.append(
                    TileRef(
                        sample_id=row["id"],
                        image_path=row["image_path"],
                        mask_path=row["mask_path"],
                        row=r,
                        col=c,
                    )
                )

    tiles_per_image = len(row_starts) * len(col_starts)
    print(
        f"Built tile index: {len(rows)} source images x "
        f"{tiles_per_image} tiles/image = {len(tile_refs)} total tiles "
        f"(tile_size={tile_size}, stride={stride}, scene_size={scene_size})."
    )
    return tile_refs, scene_size


def percentile_normalize(image: np.ndarray, low: float = PCT_LOW, high: float = PCT_HIGH) -> np.ndarray:
    """Per-image (not per-tile, not per-channel-shared) 2nd-98th percentile
    clip-and-scale to [0, 1], computed independently per channel (VV, VH
    have different dB ranges and should not share normalization stats).

    Takes the FULL scene, not a tile — this must be called before tiling,
    so all tiles from one scene share the same normalization constants.
    Calling this per-tile instead would let two tiles of the same physical
    slick end up with different brightness scaling, which is exactly the
    kind of subtle bug that silently degrades segmentation quality.
    """
    if image.ndim != 3:
        raise ValueError(f"Expected (H, W, C), got shape {image.shape}")

    normalized = np.empty_like(image, dtype=np.float32)
    for c in range(image.shape[2]):
        channel = image[:, :, c]
        lo, hi = np.percentile(channel, [low, high])
        if hi <= lo:
            # Degenerate scene (e.g. a constant-value channel) — don't
            # divide by ~zero and produce inf/nan silently.
            raise ValueError(
                f"Channel {c} has degenerate percentile range "
                f"[{lo}, {hi}] — flag this file for manual inspection "
                f"rather than training on garbage normalized output."
            )
        normalized[:, :, c] = np.clip((channel - lo) / (hi - lo), 0.0, 1.0)
    return normalized


class _SceneCache:
    """Tiny per-process LRU cache for normalized (image, mask) pairs, keyed
    by sample_id. See the module-level PERFORMANCE NOTE for why this exists.

    Each DataLoader worker gets its OWN Dataset copy (and therefore its own
    cache) — that's correct here, not a bug: we want independent small
    caches per process, not one shared cache needing synchronization.

    Sized small on purpose (default 4 full scenes ~ 128MB) — this is meant
    to survive a handful of interleaved batches between repeat requests for
    the same image within one worker, not to hold a large fraction of the
    dataset in RAM.

    scene_size, when given, is checked against every loaded image/mask —
    a second, cheap safety net behind build_tile_index()'s pre-flight
    shape check, in case a file changes on disk between that check and
    this read. Catching a mismatch here means a clear error at load time
    instead of a malformed tile silently reaching DataLoader collate.
    """

    def __init__(self, maxsize: int = DEFAULT_CACHE_SIZE, scene_size: int | None = None):
        self.maxsize = maxsize
        self.scene_size = scene_size
        self._data: "OrderedDict[str, tuple[np.ndarray, np.ndarray]]" = OrderedDict()

    def get_or_load(self, sample_id: str, image_path: str, mask_path: str):
        cached = self._data.get(sample_id)
        if cached is not None:
            self._data.move_to_end(sample_id)
            return cached

        image = tifffile.imread(image_path)   # (2048, 2048, 2) float32
        mask = tifffile.imread(mask_path)      # (2048, 2048) uint8

        if image.shape[:2] != mask.shape[:2]:
            raise ValueError(
                f"Image/mask spatial shape mismatch for sample "
                f"{sample_id}: image {image.shape} vs mask {mask.shape}."
            )
        if self.scene_size is not None and image.shape[:2] != (self.scene_size, self.scene_size):
            raise ValueError(
                f"Sample {sample_id} has shape {image.shape[:2]}, expected "
                f"({self.scene_size}, {self.scene_size}). This should have been "
                f"caught by build_tile_index()'s pre-flight check — if you're "
                f"seeing this, {image_path} changed on disk after that check ran, "
                f"or this dataset was constructed from a stale/skipped tile index."
            )

        image = percentile_normalize(image)

        self._data[sample_id] = (image, mask)
        self._data.move_to_end(sample_id)
        if len(self._data) > self.maxsize:
            self._data.popitem(last=False)  # evict least-recently-used
        return self._data[sample_id]


class GroupedShuffleSampler(Sampler[int]):
    """Shuffles at the IMAGE level, not the flat tile level.

    A plain `shuffle=True` DataLoader draws indices uniformly across all
    30,000 tiles, so consecutive requests almost never touch the same
    source image — that's what makes _SceneCache useless without this.
    This sampler instead shuffles the order of images each epoch, shuffles
    the tile positions within each image, and concatenates — so a worker's
    consecutive draws are clustered by image while still being randomized
    at both levels for training quality.

    Requires tile_refs to already be grouped by sample_id in the input
    list, which build_tile_index() guarantees.

    Call set_epoch(epoch) once per epoch (before iterating the DataLoader)
    so the shuffle order actually varies across epochs — otherwise every
    epoch would see tiles in the exact same order.
    """

    def __init__(self, tile_refs: list["TileRef"], seed: int = 0):
        groups: "OrderedDict[str, list[int]]" = OrderedDict()
        for i, ref in enumerate(tile_refs):
            groups.setdefault(ref.sample_id, []).append(i)
        self._groups: list[list[int]] = list(groups.values())
        self._n = len(tile_refs)
        self.seed = seed
        self.epoch = 0

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def __iter__(self):
        rng = random.Random(self.seed + self.epoch)
        groups = [g[:] for g in self._groups]
        for g in groups:
            rng.shuffle(g)
        rng.shuffle(groups)
        for g in groups:
            yield from g

    def __len__(self) -> int:
        return self._n


class SARTileDataset(Dataset):
    """Yields (image_tile, mask_tile) pairs as torch tensors, CHW format.

    image_tile: float32, shape (2, 512, 512), values in [0, 1]
    mask_tile:  float32, shape (1, 512, 512), values in {0, 1}
    """

    def __init__(self, tile_refs: list[TileRef], augment: bool = False,
                 cache_size: int = DEFAULT_CACHE_SIZE, scene_size: int | None = None):
        self.tile_refs = tile_refs
        self.augment = augment
        self._cache = _SceneCache(maxsize=cache_size, scene_size=scene_size)

    def __len__(self) -> int:
        return len(self.tile_refs)

    def __getitem__(self, idx: int):
        ref = self.tile_refs[idx]

        image, mask = self._cache.get_or_load(ref.sample_id, ref.image_path, ref.mask_path)

        r, c = ref.row, ref.col
        t = TILE_SIZE
        image_tile = image[r:r + t, c:c + t, :]         # (512, 512, 2)
        mask_tile = mask[r:r + t, c:c + t].astype(np.float32)  # (512, 512)

        if self.augment:
            image_tile, mask_tile = _augment(image_tile, mask_tile)

        # HWC -> CHW
        image_tile = np.transpose(image_tile, (2, 0, 1)).copy()
        mask_tile = mask_tile[np.newaxis, :, :].copy()

        return (
            torch.from_numpy(image_tile).float(),
            torch.from_numpy(mask_tile).float(),
        )


def _augment(image_tile: np.ndarray, mask_tile: np.ndarray):
    """Flip/rotation-only, per project doc §5.3 — explicitly no
    brightness/contrast augmentation, since SAR speckle statistics don't
    behave like optical-image noise and those augmentations are tuned for
    optical imagery.
    """
    if random.random() < 0.5:
        image_tile = np.flip(image_tile, axis=0)
        mask_tile = np.flip(mask_tile, axis=0)
    if random.random() < 0.5:
        image_tile = np.flip(image_tile, axis=1)
        mask_tile = np.flip(mask_tile, axis=1)
    k = random.randint(0, 3)
    if k:
        image_tile = np.rot90(image_tile, k=k, axes=(0, 1))
        mask_tile = np.rot90(mask_tile, k=k, axes=(0, 1))
    return image_tile, mask_tile


if __name__ == "__main__":
    import sys

    manifest = sys.argv[1] if len(sys.argv) > 1 else "data/processed/part1/manifest_part1.csv"

    print(f"Smoke test against {manifest} (CPU-only, no GPU needed for this check)")
    tile_index, scene_size = build_tile_index(manifest)

    ds = SARTileDataset(tile_index, augment=True, scene_size=scene_size)
    print(f"Dataset length: {len(ds)} tiles")

    img_t, mask_t = ds[0]
    print(f"First tile: image {tuple(img_t.shape)} {img_t.dtype}, "
          f"mask {tuple(mask_t.shape)} {mask_t.dtype}")
    print(f"Image value range: [{img_t.min():.4f}, {img_t.max():.4f}] "
          f"(expect within [0, 1])")
    print(f"Mask unique values: {torch.unique(mask_t).tolist()} (expect [0.0] or [0.0, 1.0])")

    # Pull a handful of random tiles to catch index-math bugs at scene edges
    import random as _random
    sample_idxs = _random.sample(range(len(ds)), min(5, len(ds)))
    for i in sample_idxs:
        img_t, mask_t = ds[i]
        assert img_t.shape == (2, TILE_SIZE, TILE_SIZE), f"Bad image shape at idx {i}: {img_t.shape}"
        assert mask_t.shape == (1, TILE_SIZE, TILE_SIZE), f"Bad mask shape at idx {i}: {mask_t.shape}"
        assert 0.0 <= img_t.min() and img_t.max() <= 1.0, f"Image out of [0,1] at idx {i}"
    print(f"Spot-checked {len(sample_idxs)} random tiles — shapes and value ranges OK.")

    # Sanity-check the sampler groups things by image as intended.
    sampler = GroupedShuffleSampler(tile_index, seed=42)
    sampler.set_epoch(0)
    order = list(sampler)
    assert len(order) == len(tile_index), "Sampler length mismatch."
    assert sorted(order) == list(range(len(tile_index))), "Sampler dropped/duplicated indices."
    print(f"GroupedShuffleSampler: {len(order)} indices, all present exactly once — OK.")
