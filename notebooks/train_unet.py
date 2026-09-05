"""
SIH26143 — Detection subsystem
Step 3: U-Net training loop. Run this on Kaggle GPU, not locally (Windows
box has no GPU per your setup — this will be brutally slow on CPU for
30,000 tiles).

Kaggle setup:
    1. Upload data/processed/part1/ (images/, masks/, manifest_part1.csv)
       as a Kaggle Dataset — don't re-extract the .7z on Kaggle, just upload
       the already-extracted+verified tiffs, since extraction is already
       done and verified locally.
    2. pip install segmentation-models-pytorch tifffile
    3. Copy this script + sar_dataset.py into the notebook.
    4. Point --manifest at wherever Kaggle mounts your dataset,
       e.g. /kaggle/input/oiltrace-part1/manifest_part1.csv
    5. Set --checkpoint-dir /kaggle/working/checkpoints (default already
       works if you run from /kaggle/working, which is Kaggle's default
       cwd). This directory is where split manifests, checkpoints, and
       everything else this script writes will go — it must NOT point
       inside /kaggle/input, which is mounted read-only.
    6. Run via "Save Version -> Save & Run All (Commit)" for the real run,
       not interactive Run All, so it survives you closing the tab.

CHANGES vs the version that was CPU-smoke-tested locally:
  - FIX: split_manifest_by_image() used to write manifest_train.csv /
    manifest_val.csv next to the input manifest. On Kaggle that's inside
    /kaggle/input, which is read-only — this would have thrown a
    PermissionError on your very first real run. It now writes into
    --checkpoint-dir instead (pass --work-dir to put it somewhere else).
  - ADDED: mixed precision (torch.cuda.amp). Meaningful speedup on
    Kaggle's T4s, which matters when you're trying to fit ~27k train
    tiles into a 12-hour session. On by default when CUDA is available;
    disable with --no-amp if you ever need to debug a numerics issue.
  - ADDED: resume support (--resume). Kaggle GPU sessions cap out at 12
    hours and the weekly GPU quota is shared across everything you run
    that week. unet_last.pt is now saved every epoch with full
    model/optimizer/scheduler/scaler state, so a killed session (or a
    run you deliberately split across two sessions) can pick back up
    exactly — not just reload the best weights and lose the Adam
    momentum + LR schedule state.
  - FIX: was single-GPU only (torch.device("cuda") always means cuda:0)
    even when a T4 x2 session is selected — the second GPU sat
    completely idle. Now wraps the model in nn.DataParallel whenever
    torch.cuda.device_count() > 1, which roughly halves wall-clock time
    per epoch on a 2-GPU session. Checkpoints always save/load the
    UNWRAPPED module's state_dict, so a checkpoint trained on 2 GPUs
    loads fine later on 1 GPU (evaluate_part3.py, a resumed single-GPU
    session, etc.) and vice versa — DataParallel is purely a training-
    time wrapper, never baked into the saved weights' key names.
  - ADDED: AdamW + configurable --weight-decay (was Adam with zero L2
    regularization). A pretrained encoder fine-tuned on a comparatively
    small dataset is a real overfitting risk without any L2 term.
  - ADDED: gradient clipping (--grad-clip, default 1.0). Dice/Tversky
    losses can spike early in training on near-random sigmoid outputs;
    this guards a long unattended commit run against a rare exploding-
    gradient step derailing it.
  - ADDED: fixed model-init seed (torch.manual_seed / np.random.seed /
    random.seed, all from RANDOM_SEED). Needed for the --loss dice_bce
    vs --loss focal_tversky A/B to actually be apples-to-apples — without
    this, the decoder's random init differs between the two runs, which
    confounds the comparison.
  - ADDED: stratified train/val split. If the manifest has a
    'source_prefix' or 'category' column (combine_kaggle_manifests.py
    now writes 'source_prefix'), the split is done independently within
    each stratum and concatenated, so a merged Part I + Part II manifest
    can't accidentally produce a validation set skewed toward one part.
    Falls back to the original unstratified split if neither column is
    present (e.g. a plain single-part manifest).
  - ADDED: optional early stopping (--early-stop-patience, off by
    default). unet_best.pt already captures the peak regardless, so this
    is purely a quota-saving option, not a correctness fix — training
    past the peak doesn't hurt the checkpoint you actually ship.

IMPORTANT — train/val split is done at the IMAGE level (by sample_id),
never at the tile level. Splitting tiles randomly would put overlapping
tiles from the SAME source image in both train and val (since stride=384 <
tile_size=512 means adjacent tiles share pixels) — that's data leakage,
and it would make validation IoU look better than the model actually is.
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import segmentation_models_pytorch as smp
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from sar_dataset import GroupedShuffleSampler, SARTileDataset, TileRef, build_tile_index

VAL_FRACTION = 0.1
RANDOM_SEED = 42


def split_manifest_by_image(manifest_csv: str, val_fraction: float, seed: int, output_dir: str):
    """Splits at the image (sample_id) level and writes two temp manifest
    files, so build_tile_index can be reused unmodified on each split.

    STRATIFIED when possible: if the manifest has a 'source_prefix' or
    'category' column, the split is done independently within each
    stratum (e.g. oiltrace-part1 vs oiltrace-part2) and concatenated —
    this stops a merged multi-part manifest from accidentally producing a
    validation set skewed toward one part just by chance. Falls back to
    a plain unstratified split if neither column exists.

    output_dir must be writable — on Kaggle this means /kaggle/working
    (or a subdirectory of it), never /kaggle/input, which is read-only.
    """
    manifest_csv = Path(manifest_csv)
    with open(manifest_csv, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    strata_key = "source_prefix" if "source_prefix" in fieldnames else (
        "category" if "category" in fieldnames else None
    )

    rng = random.Random(seed)
    val_ids: set[str] = set()

    if strata_key:
        groups: "defaultdict[str, list[str]]" = defaultdict(list)
        for r in rows:
            groups[r[strata_key]].append(r["id"])
        for stratum, ids_in_group in groups.items():
            ids_in_group = ids_in_group[:]
            rng.shuffle(ids_in_group)
            n_val_group = max(1, int(len(ids_in_group) * val_fraction))
            val_ids.update(ids_in_group[:n_val_group])
        print(f"Stratified split by '{strata_key}': "
              + ", ".join(f"{k}={len(v)}" for k, v in groups.items()))
    else:
        ids = [r["id"] for r in rows]
        rng.shuffle(ids)
        n_val = max(1, int(len(ids) * val_fraction))
        val_ids = set(ids[:n_val])

    ids = [r["id"] for r in rows]
    train_ids = set(ids) - val_ids

    train_rows = [r for r in rows if r["id"] in train_ids]
    val_rows = [r for r in rows if r["id"] in val_ids]

    assert train_ids.isdisjoint(val_ids), "BUG: train/val id overlap — leakage."

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "manifest_train.csv"
    val_path = output_dir / "manifest_val.csv"

    for path, rows_out in [(train_path, train_rows), (val_path, val_rows)]:
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "image_path", "mask_path"])
            w.writeheader()
            w.writerows({"id": r["id"], "image_path": r["image_path"], "mask_path": r["mask_path"]}
                        for r in rows_out)

    print(f"Split {len(ids)} images -> {len(train_ids)} train / {len(val_ids)} val "
          f"(seed={seed}). Written to {train_path}, {val_path}.")
    return train_path, val_path


class DiceBCELoss(nn.Module):
    """Combined Dice + BCEWithLogitsLoss, per project doc §5.3 — plain BCE
    or cross-entropy alone under-trains on the minority oil-pixel class
    since most pixels in any scene are water.
    """

    def __init__(self, dice_weight: float = 0.5, bce_weight: float = 0.5, smooth: float = 1.0):
        super().__init__()
        self.dice_weight = dice_weight
        self.bce_weight = bce_weight
        self.smooth = smooth
        self.bce = nn.BCEWithLogitsLoss()

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # BUG FIX (found via a synthetic overflow test, not observed on
        # Kaggle): under torch.cuda.amp.autocast, BCEWithLogitsLoss is
        # automatically forced to fp32 internally by PyTorch's autocast
        # policy because it's numerically sensitive — but this hand-rolled
        # Dice reduction has no such protection and was running in fp16.
        # A 512x512 tile has 262,144 pixels; summing that many ~0.5 values
        # (typical for a near-random, early-training sigmoid output) gives
        # ~131,000 — which overflows fp16's max representable value of
        # 65,504 straight to inf, turning dice_coef into nan on nearly
        # every early batch. GradScaler does NOT fix this: it only guards
        # backward-pass gradients, not an already-nan forward value, so
        # this would have silently stalled training (nan loss, optimizer
        # step skipped every time) for the entire run. Fix: force this
        # reduction to run in fp32 regardless of the surrounding autocast
        # context, using autocast(enabled=False) + explicit .float() casts.
        with torch.cuda.amp.autocast(enabled=False):
            logits_fp32 = logits.float()
            targets_fp32 = targets.float()

            bce_loss = self.bce(logits_fp32, targets_fp32)

            probs = torch.sigmoid(logits_fp32)
            probs_flat = probs.reshape(probs.shape[0], -1)
            targets_flat = targets_fp32.reshape(targets_fp32.shape[0], -1)

            intersection = (probs_flat * targets_flat).sum(dim=1)
            dice_coef = (2.0 * intersection + self.smooth) / (
                probs_flat.sum(dim=1) + targets_flat.sum(dim=1) + self.smooth
            )
            dice_loss = 1.0 - dice_coef.mean()

            return self.bce_weight * bce_loss + self.dice_weight * dice_loss


class FocalTverskyLoss(nn.Module):
    """Optional alternative to DiceBCELoss, opt-in via --loss focal_tversky.
    Not the default — DiceBCELoss above is the validated, working loss;
    this exists so you can A/B it cheaply (one epoch on Kaggle) rather than
    replace something that's already producing a reasonable val_oil_IoU.

    Tversky loss generalizes Dice with independent false-positive (alpha)
    and false-negative (beta) weights. For oil-spill detection, a missed
    real slick (false negative) is a worse outcome than a false alarm on
    something look-alike (false positive) — alpha < beta biases the loss
    toward penalizing missed oil harder, which plain Dice/BCE doesn't do
    (Dice implicitly weights FP and FN equally). The gamma exponent
    (focal term) additionally up-weights harder, low-Tversky-score
    examples during training, which matters here because most tiles are
    "easy" (no oil at all) once Part II negatives are merged in.

    Same fp32-forced-under-autocast pattern as DiceBCELoss above, for the
    same reason: this reduction oversums logits/probs across a 512x512
    tile and will silently NaN in fp16 under mixed precision otherwise.
    """

    def __init__(self, alpha: float = 0.3, beta: float = 0.7, gamma: float = 1.0, smooth: float = 1.0):
        super().__init__()
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.smooth = smooth

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        with torch.cuda.amp.autocast(enabled=False):
            probs = torch.sigmoid(logits.float())
            targets = targets.float()
            probs_flat = probs.reshape(probs.shape[0], -1)
            targets_flat = targets.reshape(targets.shape[0], -1)

            tp = (probs_flat * targets_flat).sum(dim=1)
            fp = (probs_flat * (1 - targets_flat)).sum(dim=1)
            fn = ((1 - probs_flat) * targets_flat).sum(dim=1)

            tversky = (tp + self.smooth) / (
                tp + self.alpha * fp + self.beta * fn + self.smooth
            )
            focal_tversky = (1.0 - tversky) ** self.gamma
            return focal_tversky.mean()


def compute_false_positive_rate(logits: torch.Tensor, targets: torch.Tensor, threshold: float = 0.5) -> float:
    """Fraction of pixels wrongly predicted as oil, computed ONLY over
    batches whose ground-truth mask is entirely zero (no real oil present).
    This is the number a judge will ask about directly — "how often does
    it false-alarm on something that looks like oil but isn't" — separate
    from oil_IoU, which only ever looks at oil-containing scenes and says
    nothing about false-alarm behavior on its own.

    Returns nan if this batch contains no all-zero-mask samples (e.g. mid-
    training before Part II negatives are merged in, when every Part I
    scene has at least some oil pixels) — same "nan means undefined, not
    zero" convention as compute_oil_iou, for the same reason.
    """
    preds = (torch.sigmoid(logits.float()) > threshold).float()
    targets = targets.float()
    is_negative = targets.sum(dim=(1, 2, 3)) == 0
    if is_negative.sum() == 0:
        return float("nan")
    fp_pixels = preds[is_negative].mean(dim=(1, 2, 3))
    return fp_pixels.mean().item()


@torch.no_grad()
def compute_oil_iou(logits: torch.Tensor, targets: torch.Tensor, threshold: float = 0.5) -> float:
    """Oil-class IoU (not pixel accuracy) — per project doc §5.3, pixel
    accuracy is nearly free/meaningless here since most pixels are water.
    Returns IoU only over batches that actually contain oil pixels in the
    target; batches with an all-zero mask are excluded from THIS metric's
    average (their IoU is undefined, not zero — treating it as zero would
    incorrectly penalize the model for correctly predicting "no oil" on a
    genuinely oil-free tile).
    """
    preds = (torch.sigmoid(logits.float()) > threshold).float()
    targets = targets.float()
    intersection = (preds * targets).sum(dim=(1, 2, 3))
    union = ((preds + targets) > 0).float().sum(dim=(1, 2, 3))

    has_oil = targets.sum(dim=(1, 2, 3)) > 0
    if has_oil.sum() == 0:
        return float("nan")  # no oil-containing tiles in this batch

    iou_per_sample = intersection[has_oil] / union[has_oil].clamp(min=1e-6)
    return iou_per_sample.mean().item()


def train(args):
    # Seed everything, not just the data split/sampler — needed so the
    # --loss dice_bce vs --loss focal_tversky A/B is actually apples-to-
    # apples (same decoder init, same augmentation coin-flips) instead of
    # confounded by two different random model initializations.
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    torch.manual_seed(RANDOM_SEED)
    torch.cuda.manual_seed_all(RANDOM_SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu":
        print("*** WARNING: no CUDA device found. This will be extremely slow "
              "for 30,000 tiles. Confirm you're running this on Kaggle GPU, "
              "not locally, before letting a full run proceed. ***")

    amp_enabled = (device.type == "cuda") and not args.no_amp
    print(f"Device: {device}, mixed precision: {amp_enabled}")

    ckpt_dir = Path(args.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    work_dir = args.work_dir or args.checkpoint_dir
    train_manifest, val_manifest = split_manifest_by_image(
        args.manifest, VAL_FRACTION, RANDOM_SEED, work_dir
    )

    train_tiles, train_scene_size = build_tile_index(train_manifest, tile_size=512, stride=args.stride)
    val_tiles, val_scene_size = build_tile_index(val_manifest, tile_size=512, stride=512)  # no overlap needed for val

    train_ds = SARTileDataset(train_tiles, augment=True, scene_size=train_scene_size)
    val_ds = SARTileDataset(val_tiles, augment=False, scene_size=val_scene_size)

    # GroupedShuffleSampler instead of shuffle=True: keeps a worker's
    # consecutive tile requests clustered by source image so
    # SARTileDataset's per-worker scene cache actually gets hits, instead
    # of a fully-random tile order re-reading the same ~32MB scene ~25x
    # per epoch. See sar_dataset.py's module docstring for the numbers.
    train_sampler = GroupedShuffleSampler(train_tiles, seed=RANDOM_SEED)
    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, sampler=train_sampler,
        num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
        drop_last=True,
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
    )

    model = smp.Unet(
        encoder_name="resnet34",
        encoder_weights="imagenet",
        in_channels=2,   # VV + VH — confirmed real shape, not RGB
        classes=1,
    ).to(device)

    n_gpus = torch.cuda.device_count() if device.type == "cuda" else 0
    if n_gpus > 1:
        print(f"{n_gpus} GPUs visible — wrapping model in nn.DataParallel so both "
              f"are actually used (a plain torch.device('cuda') call only ever uses "
              f"GPU 0, leaving the rest idle on a multi-GPU session). Consider raising "
              f"--batch-size (e.g. {args.batch_size * n_gpus}) to keep each GPU as "
              f"busy as it was at the original batch size.")
        model = nn.DataParallel(model)
    # Always used for state_dict save/load, regardless of DataParallel —
    # this keeps checkpoint key names identical whether trained on 1 or
    # N GPUs, so a checkpoint from this run loads fine later in
    # evaluate_part3.py or a resumed single-GPU session.
    raw_model = model.module if isinstance(model, nn.DataParallel) else model

    if args.loss == "focal_tversky":
        criterion = FocalTverskyLoss(alpha=args.tversky_alpha, beta=args.tversky_beta)
        print(f"Using FocalTverskyLoss (alpha={args.tversky_alpha}, beta={args.tversky_beta}, "
              f"recall-weighted since beta > alpha means missed oil is penalized harder than false alarms)")
    else:
        criterion = DiceBCELoss()
    # AdamW (decoupled weight decay) instead of plain Adam: a pretrained
    # encoder fine-tuned on a comparatively small dataset has real
    # overfitting risk with zero L2 regularization. --weight-decay 0
    # recovers the old Adam-equivalent behavior if you ever want it.
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=3
    )
    scaler = torch.cuda.amp.GradScaler(enabled=amp_enabled)

    start_epoch = 1
    best_val_iou = -1.0
    epochs_since_improvement = 0

    if args.resume:
        print(f"Resuming from {args.resume}")
        ckpt = torch.load(args.resume, map_location=device)
        raw_model.load_state_dict(ckpt["model_state_dict"])
        optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        scheduler.load_state_dict(ckpt["scheduler_state_dict"])
        if amp_enabled and ckpt.get("scaler_state_dict"):
            scaler.load_state_dict(ckpt["scaler_state_dict"])
        start_epoch = ckpt["epoch"] + 1
        best_val_iou = ckpt.get("best_val_iou", -1.0)
        epochs_since_improvement = ckpt.get("epochs_since_improvement", 0)
        print(f"Resumed at epoch {start_epoch}, best_val_iou so far={best_val_iou:.4f}")

    if start_epoch > args.epochs:
        print(f"Checkpoint is already at epoch {start_epoch - 1} >= --epochs "
              f"{args.epochs}. Nothing to do — raise --epochs to continue training.")
        return

    for epoch in range(start_epoch, args.epochs + 1):
        train_sampler.set_epoch(epoch)  # vary shuffle order across epochs
        model.train()
        running_loss = 0.0
        for batch_idx, (images, masks) in enumerate(train_loader):
            images, masks = images.to(device), masks.to(device)

            optimizer.zero_grad()
            with torch.cuda.amp.autocast(enabled=amp_enabled):
                logits = model(images)
                loss = criterion(logits, masks)
            scaler.scale(loss).backward()
            if args.grad_clip and args.grad_clip > 0:
                # Must unscale before clipping, or we'd be clipping the
                # scaled (artificially large) gradients from AMP instead
                # of the real ones.
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            scaler.step(optimizer)
            scaler.update()

            running_loss += loss.item()
            if batch_idx % args.log_every == 0:
                print(f"Epoch {epoch} [{batch_idx}/{len(train_loader)}] "
                      f"loss={loss.item():.4f}")

        avg_train_loss = running_loss / len(train_loader)

        model.eval()
        val_ious = []
        val_fp_rates = []
        with torch.no_grad():
            for images, masks in val_loader:
                images, masks = images.to(device), masks.to(device)
                with torch.cuda.amp.autocast(enabled=amp_enabled):
                    logits = model(images)
                iou = compute_oil_iou(logits, masks)
                if not np.isnan(iou):
                    val_ious.append(iou)
                fp_rate = compute_false_positive_rate(logits, masks)
                if not np.isnan(fp_rate):
                    val_fp_rates.append(fp_rate)

        mean_val_iou = float(np.mean(val_ious)) if val_ious else float("nan")
        mean_fp_rate = float(np.mean(val_fp_rates)) if val_fp_rates else float("nan")
        fp_note = (f", val_false_positive_rate={mean_fp_rate:.5f} "
                    f"(over {len(val_fp_rates)}/{len(val_loader)} no-oil val batches)"
                    if val_fp_rates else
                    ", val_false_positive_rate=n/a (no all-zero-mask scenes in this "
                    "manifest yet — expected until Part II negatives are merged in)")
        print(f"=== Epoch {epoch}: train_loss={avg_train_loss:.4f}, "
              f"val_oil_IoU={mean_val_iou:.4f} "
              f"(over {len(val_ious)}/{len(val_loader)} oil-containing val batches)"
              f"{fp_note} ===")

        if not np.isnan(mean_val_iou):
            scheduler.step(mean_val_iou)
            if mean_val_iou > best_val_iou:
                best_val_iou = mean_val_iou
                epochs_since_improvement = 0
                ckpt_path = ckpt_dir / "unet_best.pt"
                torch.save({
                    "epoch": epoch,
                    "model_state_dict": raw_model.state_dict(),
                    "val_oil_iou": mean_val_iou,
                    "loss": args.loss,
                }, ckpt_path)
                print(f"New best val_oil_IoU={mean_val_iou:.4f} — saved to {ckpt_path}")
            else:
                epochs_since_improvement += 1
        else:
            epochs_since_improvement += 1

        # Rolling "last" checkpoint, saved every epoch regardless of
        # improvement — this is what --resume loads. Includes optimizer/
        # scheduler/scaler state so resuming continues training exactly,
        # not just from the right weights with a reset Adam/LR state.
        last_ckpt_path = ckpt_dir / "unet_last.pt"
        torch.save({
            "epoch": epoch,
            "model_state_dict": raw_model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "scaler_state_dict": scaler.state_dict() if amp_enabled else None,
            "val_oil_iou": mean_val_iou,
            "best_val_iou": best_val_iou,
            "epochs_since_improvement": epochs_since_improvement,
            "loss": args.loss,
        }, last_ckpt_path)

        if args.early_stop_patience and epochs_since_improvement >= args.early_stop_patience:
            print(f"\nNo val_oil_IoU improvement for {epochs_since_improvement} epochs "
                  f"(--early-stop-patience {args.early_stop_patience}) — stopping early at "
                  f"epoch {epoch}/{args.epochs}. unet_best.pt already has the peak checkpoint; "
                  f"this only saves the remaining GPU quota, it doesn't change what you'd ship.")
            break

    print(f"\nTraining complete. Best val_oil_IoU={best_val_iou:.4f}")
    print("NOTE: this loop trains on Part I only. Part II look-alikes "
          "(all-zero-mask hard negatives) are NOT yet included — see "
          "add_lookalikes_as_negatives() below for how to fold them in "
          "once Part II finishes downloading, without restructuring this script.")


def add_lookalikes_as_negatives(part1_manifest: str, part2_manifest: str, output_manifest: str):
    """Concatenates Part II's look-alike manifest onto Part I's, so
    build_tile_index treats them identically — Part II images ship with an
    all-zero mask already (per project doc §5.2), so no special-casing is
    needed in the Dataset/loss code. This is intentionally a separate,
    optional step, not baked into train() by default, so you can validate
    the Part-I-only loop works BEFORE adding a second dataset's worth of
    files into the mix.

    Call this once Part II is downloaded, verified (reuse
    extract_and_inspect_part1.py's approach — confirm all-zero masks are
    genuinely all-zero, not just mostly-zero), and has its own manifest CSV
    in the same {id,image_path,mask_path} shape.
    """
    with open(part1_manifest, newline="") as f:
        rows = list(csv.DictReader(f))
    with open(part2_manifest, newline="") as f:
        rows += list(csv.DictReader(f))

    with open(output_manifest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "image_path", "mask_path"])
        w.writeheader()
        w.writerows(rows)

    print(f"Combined manifest written to {output_manifest}: {len(rows)} total images.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, default="data/processed/part1/manifest_part1.csv")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4,
                         help="AdamW L2 regularization. 0 recovers old Adam-equivalent behavior.")
    parser.add_argument("--grad-clip", type=float, default=1.0,
                         help="Max gradient norm. 0 or negative disables clipping.")
    parser.add_argument("--early-stop-patience", type=int, default=None,
                         help="Stop if val_oil_IoU hasn't improved for this many epochs. "
                              "Off by default (trains the full --epochs count) — unet_best.pt "
                              "already captures the peak either way, this only saves quota.")
    parser.add_argument("--stride", type=int, default=384)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--checkpoint-dir", type=str, default="checkpoints")
    parser.add_argument("--work-dir", type=str, default=None,
                         help="Where to write the train/val manifest split. "
                              "Defaults to --checkpoint-dir. Must be writable — "
                              "never point this inside /kaggle/input.")
    parser.add_argument("--resume", type=str, default=None,
                         help="Path to unet_last.pt to resume training from "
                              "(e.g. after a Kaggle session was killed at the "
                              "12-hour cap).")
    parser.add_argument("--no-amp", action="store_true",
                         help="Disable mixed precision (on by default on CUDA).")
    parser.add_argument("--loss", type=str, default="dice_bce", choices=["dice_bce", "focal_tversky"],
                         help="dice_bce (default, validated) or focal_tversky (opt-in, "
                              "recall-weighted — penalizes missed oil harder than false "
                              "alarms; A/B against dice_bce on a real epoch before committing to it).")
    parser.add_argument("--tversky-alpha", type=float, default=0.3,
                         help="False-positive weight for focal_tversky loss. Lower = more tolerant of false alarms.")
    parser.add_argument("--tversky-beta", type=float, default=0.7,
                         help="False-negative weight for focal_tversky loss. Higher = penalizes missed oil harder.")
    args = parser.parse_args()

    train(args)
