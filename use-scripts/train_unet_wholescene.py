"""
SIH26143 — Detection subsystem
train_unet_wholescene.py — segmentation training using whole-scene
resize (matching Trujillo-Acatitla et al.'s actual reported method)
instead of sar_dataset.py's tiled-crop approach. See
whole_scene_dataset.py's module docstring for the full reasoning.

This is a SIBLING to train_unet.py, not a replacement — run both and
compare val_oil_IoU on the same held-out split before deciding which one
you ship. Reuses train_unet.py's loss functions (DiceBCELoss, FocalLoss,
FocalTverskyLoss) directly via import, so the loss math is guaranteed
identical between the two scripts — only the input pipeline (whole-scene
vs tiled) and a couple of paper-matching architecture defaults differ.

PAPER-MATCHING DEFAULTS CHANGED FROM train_unet.py:
  - --loss defaults to "focal" here, not "dice_bce" — Focal Loss is what
    the paper's own authors credited as their single biggest lever
    (train_unet.py's default is dice_bce because that's the one that's
    actually been validated end-to-end in THIS project so far; focal is
    still only 1-epoch-tested per the handoff doc, so treat this
    whole-scene run as the clean place to finally get a real multi-epoch
    read on it).
  - --decoder-width defaults to "wide" here — "more layers and filters"
    is explicitly what the paper credits alongside Focal Loss.
  - --encoder-weights defaults to "imagenet" (transfer learning), NOT
    matching the paper (they trained from scratch, specifically to avoid
    RGB-pretrained bias on 2-channel SAR input). Pass
    --encoder-weights none to match the paper exactly and A/B it — with a
    dataset this size, pretrained-vs-scratch is a genuinely open question,
    not a settled one, so both are one flag away from each other here.

USAGE (Kaggle, oil-only cascade retrain — the recommended first run):
    !python build_oil_only_manifest.py \
        --manifest /kaggle/working/manifest_train_combined.csv \
        --output /kaggle/working/manifest_oil_only.csv
    !python train_unet_wholescene.py \
        --manifest /kaggle/working/manifest_oil_only.csv \
        --epochs 20 --batch-size 16 \
        --checkpoint-dir /kaggle/working/checkpoints_wholescene_oilonly

USAGE (mixed/realistic manifest, for the honest end-to-end comparison):
    !python train_unet_wholescene.py \
        --manifest /kaggle/working/manifest_train_combined.csv \
        --epochs 20 --batch-size 16 \
        --checkpoint-dir /kaggle/working/checkpoints_wholescene_mixed
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

from train_unet import DiceBCELoss, FocalLoss, FocalTverskyLoss, DECODER_WIDTH_PRESETS
from whole_scene_dataset import SARWholeSceneDataset, load_wholescene_manifest

VAL_FRACTION = 0.1
RANDOM_SEED = 42


def split_rows_by_image(rows: list[dict], val_fraction: float, seed: int):
    """Same stratified-by-source_prefix split logic as train_unet.py's
    split_manifest_by_image, but operating on in-memory rows directly
    (no temp-file round trip needed — whole-scene loading doesn't need
    build_tile_index's manifest-file-based API)."""
    rng = random.Random(seed)
    strata_key = "source_prefix" if rows and "source_prefix" in rows[0] else (
        "category" if rows and "category" in rows[0] else None
    )
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
        print(f"Stratified split by '{strata_key}': " + ", ".join(f"{k}={len(v)}" for k, v in groups.items()))
    else:
        ids = [r["id"] for r in rows]
        rng.shuffle(ids)
        n_val = max(1, int(len(ids) * val_fraction))
        val_ids = set(ids[:n_val])

    train_rows = [r for r in rows if r["id"] not in val_ids]
    val_rows = [r for r in rows if r["id"] in val_ids]
    assert len(train_rows) + len(val_rows) == len(rows)
    print(f"Split {len(rows)} images -> {len(train_rows)} train / {len(val_rows)} val (seed={seed}).")
    return train_rows, val_rows


def train(args):
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    torch.manual_seed(RANDOM_SEED)
    torch.cuda.manual_seed_all(RANDOM_SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu":
        print("*** WARNING: no CUDA device found. Confirm you're on Kaggle GPU before "
              "letting a full run proceed. ***")
    amp_enabled = (device.type == "cuda") and not args.no_amp
    print(f"Device: {device}, mixed precision: {amp_enabled}")

    ckpt_dir = Path(args.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    rows = load_wholescene_manifest(args.manifest)
    train_rows, val_rows = split_rows_by_image(rows, VAL_FRACTION, RANDOM_SEED)

    train_ds = SARWholeSceneDataset(train_rows, augment=True, despeckle=args.despeckle)
    val_ds = SARWholeSceneDataset(val_rows, augment=False, despeckle=args.despeckle)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                               num_workers=args.num_workers, pin_memory=(device.type == "cuda"),
                               drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                             num_workers=args.num_workers, pin_memory=(device.type == "cuda"))

    encoder_weights = None if args.encoder_weights == "none" else args.encoder_weights
    model = smp.Unet(
        encoder_name="resnet34",
        encoder_weights=encoder_weights,
        in_channels=2,
        classes=1,
        decoder_channels=DECODER_WIDTH_PRESETS[args.decoder_width],
        decoder_attention_type=(args.decoder_attention if args.decoder_attention != "none" else None),
    ).to(device)
    if encoder_weights is None:
        print("Training encoder FROM SCRATCH (--encoder-weights none) — matches the "
              "paper's own choice. Expect more epochs needed to converge than with a "
              "pretrained encoder.")

    n_gpus = torch.cuda.device_count() if device.type == "cuda" else 0
    if n_gpus > 1:
        print(f"{n_gpus} GPUs visible — wrapping in nn.DataParallel.")
        model = nn.DataParallel(model)
    raw_model = model.module if isinstance(model, nn.DataParallel) else model

    # --init-checkpoint: load ONLY model weights (no optimizer/scheduler/epoch
    # state) — this is the CURRICULUM/WARM-START path. Use it to fine-tune a
    # mixed-manifest run starting from an oil-only-trained checkpoint's
    # weights: the model already understands "what oil texture looks like"
    # from the easier subproblem, and only has to additionally learn "and
    # suppress it when it's genuinely absent" — usually a much more stable
    # starting point than random/ImageNet init for the harder mixed task,
    # and the reason the mixed run (started from ImageNet-only weights)
    # overfit and oscillated after epoch 6 rather than converging further.
    #
    # --resume is different: it restores FULL training state (optimizer,
    # scheduler, scaler, epoch count) to literally continue an interrupted
    # or intentionally-partial run of the SAME manifest/config — use this to
    # keep training the oil-only run past its own last epoch, not to jump
    # to a different manifest.
    #
    # If both are given, --resume wins (it's the more complete state) and
    # --init-checkpoint is ignored with a warning — they answer different
    # questions and mixing them silently would be confusing.
    start_epoch = 1
    if args.resume:
        print(f"--resume: loading FULL training state from {args.resume}")
        ckpt = torch.load(args.resume, map_location=device)
        raw_model.load_state_dict(ckpt["model_state_dict"])
        start_epoch = ckpt.get("epoch", 0) + 1
        print(f"Resuming from end of epoch {ckpt.get('epoch')} -> starting at epoch {start_epoch}.")
        if args.init_checkpoint:
            print("--init-checkpoint was also given but --resume takes priority; ignoring --init-checkpoint.")
    elif args.init_checkpoint:
        print(f"--init-checkpoint: warm-starting MODEL WEIGHTS ONLY from {args.init_checkpoint} "
              f"(optimizer/scheduler/epoch count start fresh — this is a curriculum warm-start, "
              f"not a resume).")
        ckpt = torch.load(args.init_checkpoint, map_location=device)
        # strict=False deliberately: --init-checkpoint is also how you add a new module
        # (e.g. --decoder-attention scse) on top of weights trained WITHOUT it. The
        # source checkpoint won't have SCSE's attention-gate parameters at all, so a
        # strict load would hard-crash on missing keys. With strict=False, every
        # matching key (encoder + decoder conv weights) loads the trained values, and
        # only the genuinely NEW parameters (the attention gates) stay at their random
        # init — exactly the intended behavior: reuse everything already learned, let
        # only the new mechanism start from scratch. If you're NOT changing architecture
        # (same decoder-width/attention as the source checkpoint), missing/unexpected
        # should both print as 0 below — if they don't in that case, something else is
        # actually mismatched and worth investigating before trusting this run.
        missing, unexpected = raw_model.load_state_dict(ckpt["model_state_dict"], strict=False)
        print(f"Loaded with strict=False: {len(missing)} missing key(s), {len(unexpected)} unexpected key(s).")
        if missing:
            preview = missing[:8]
            print(f"  missing (left at random init — expected for newly-added modules like "
                  f"SCSE attention gates): {preview}{' ...' if len(missing) > 8 else ''}")
        if unexpected:
            preview = unexpected[:8]
            print(f"  unexpected (present in checkpoint but not in this model — dropped): "
                  f"{preview}{' ...' if len(unexpected) > 8 else ''}")

    if args.loss == "focal_tversky":
        criterion = FocalTverskyLoss(alpha=args.tversky_alpha, beta=args.tversky_beta)
    elif args.loss == "focal":
        criterion = FocalLoss(alpha=args.focal_alpha, gamma=args.focal_gamma)
        print(f"Using FocalLoss (alpha={args.focal_alpha}, gamma={args.focal_gamma}) — "
              f"the paper's own credited lever, now getting a real whole-scene, "
              f"multi-epoch test.")
    else:
        criterion = DiceBCELoss()

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=3)
    scaler = torch.cuda.amp.GradScaler(enabled=amp_enabled)

    best_val_iou = -1.0
    if args.resume:
        if ckpt.get("optimizer_state_dict"):
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        if ckpt.get("scheduler_state_dict"):
            scheduler.load_state_dict(ckpt["scheduler_state_dict"])
        if amp_enabled and ckpt.get("scaler_state_dict"):
            scaler.load_state_dict(ckpt["scaler_state_dict"])
        best_val_iou = ckpt.get("best_val_iou", ckpt.get("val_oil_iou", -1.0))
        print(f"Restored optimizer/scheduler/scaler state. best_val_iou so far = {best_val_iou:.4f}")

    if start_epoch > args.epochs:
        raise SystemExit(f"--resume checkpoint is already past epoch {args.epochs} "
                          f"(at epoch {start_epoch - 1}) — raise --epochs to continue training.")

    epochs_since_improve = 0
    for epoch in range(start_epoch, args.epochs + 1):
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
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            scaler.step(optimizer)
            scaler.update()
            running_loss += loss.item()
            if batch_idx % args.log_every == 0:
                print(f"Epoch {epoch} [{batch_idx}/{len(train_loader)}] loss={loss.item():.4f}")
        avg_train_loss = running_loss / len(train_loader)

        # Corpus-level micro-averaged IoU — same convention as
        # train_unet.py's (fixed) validation metric. At one scene per
        # sample here (not 25 tiles), this is naturally less noisy than
        # the tile-based version even before accounting for anything else.
        model.eval()
        total_inter, total_union = 0.0, 0.0
        fp_pixels_sum, fp_pixels_count = 0.0, 0
        with torch.no_grad():
            for images, masks in val_loader:
                images, masks = images.to(device), masks.to(device)
                with torch.cuda.amp.autocast(enabled=amp_enabled):
                    logits = model(images)
                preds = (torch.sigmoid(logits.float()) > 0.5).float()
                targets = (masks.float() > 0.5).float()  # threshold the soft resized mask for metric purposes

                inter = (preds * targets).sum(dim=(1, 2, 3))
                union = ((preds + targets) > 0).float().sum(dim=(1, 2, 3))
                total_inter += inter.sum().item()
                total_union += union.sum().item()

                is_negative = targets.sum(dim=(1, 2, 3)) == 0
                if is_negative.sum() > 0:
                    fp_pixels_sum += preds[is_negative].sum().item()
                    fp_pixels_count += is_negative.sum().item() * preds.shape[-1] * preds.shape[-2]

        mean_val_iou = total_inter / max(total_union, 1e-6)
        fp_rate = fp_pixels_sum / max(fp_pixels_count, 1) if fp_pixels_count > 0 else float("nan")
        print(f"=== Epoch {epoch}: train_loss={avg_train_loss:.4f}, "
              f"val_oil_IoU={mean_val_iou:.4f} (corpus micro-averaged, whole-scene), "
              f"val_false_positive_rate={fp_rate:.5f} ===")

        if not np.isnan(mean_val_iou):
            scheduler.step(mean_val_iou)
            if mean_val_iou > best_val_iou:
                best_val_iou = mean_val_iou
                epochs_since_improve = 0
                torch.save({
                    "epoch": epoch,
                    "model_state_dict": raw_model.state_dict(),
                    "val_oil_iou": mean_val_iou,
                    "loss": args.loss,
                    "input_mode": "whole_scene",
                }, ckpt_dir / "unet_wholescene_best.pt")
                print(f"New best val_oil_IoU={mean_val_iou:.4f} — saved.")
            else:
                epochs_since_improve += 1
                if args.early_stop_patience and epochs_since_improve >= args.early_stop_patience:
                    print(f"\nNo improvement in val_oil_IoU for {epochs_since_improve} epochs "
                          f"(--early-stop-patience={args.early_stop_patience}) — stopping early "
                          f"at epoch {epoch}. Best remains {best_val_iou:.4f}. This is exactly the "
                          f"kind of plateau-then-oscillate pattern seen in the mixed-manifest run "
                          f"(peaked epoch 6, never recovered through epoch 25) — stopping here "
                          f"instead of burning quota on epochs that won't beat it.")
                    torch.save({
                        "epoch": epoch,
                        "model_state_dict": raw_model.state_dict(),
                        "optimizer_state_dict": optimizer.state_dict(),
                        "scheduler_state_dict": scheduler.state_dict(),
                        "scaler_state_dict": scaler.state_dict() if amp_enabled else None,
                        "val_oil_iou": mean_val_iou,
                        "best_val_iou": best_val_iou,
                        "loss": args.loss,
                        "input_mode": "whole_scene",
                    }, ckpt_dir / "unet_wholescene_last.pt")
                    break

        torch.save({
            "epoch": epoch,
            "model_state_dict": raw_model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "scaler_state_dict": scaler.state_dict() if amp_enabled else None,
            "val_oil_iou": mean_val_iou,
            "best_val_iou": best_val_iou,
            "loss": args.loss,
            "input_mode": "whole_scene",
        }, ckpt_dir / "unet_wholescene_last.pt")

    print(f"\nTraining complete. Best val_oil_IoU={best_val_iou:.4f}")
    print("IMPORTANT: this checkpoint expects WHOLE-SCENE-RESIZED 512x512 input "
          "(same preprocessing as SARWholeSceneDataset), NOT tiled crops from "
          "sar_dataset.py. evaluate_part3.py must resize each full scene the same "
          "way before feeding it to this checkpoint — reusing predict_full_scene() "
          "built for tile-stitching will silently misfeed this model. This needs a "
          "small evaluate_part3.py update (a --input-mode flag mirroring this one) "
          "before running the final held-out evaluation on a whole-scene checkpoint.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True,
                         help="Manifest CSV. Point this at the OIL-ONLY manifest from "
                              "build_oil_only_manifest.py for the cascade stage-2 retrain, "
                              "or at the full mixed manifest for the realistic-scenario comparison.")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16,
                         help="Whole-scene 512x512 samples are ~4x fewer per image than tiled "
                              "(1 vs ~25), so a larger batch size than train_unet.py's default "
                              "is usually affordable at the same memory budget — tune to your GPU.")
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4,
                         help="NOTE: if --loss focal, drop this to ~1e-6 — see project doc §5.5 "
                              "for why AdamW's fixed-rate weight decay dominates Focal Loss's "
                              "much smaller gradients once background pixels become 'easy'.")
    parser.add_argument("--grad-clip", type=float, default=1.0)
    parser.add_argument("--decoder-width", type=str, default="wide", choices=list(DECODER_WIDTH_PRESETS.keys()))
    parser.add_argument("--decoder-attention", type=str, default="none", choices=["none", "scse"])
    parser.add_argument("--encoder-weights", type=str, default="imagenet", choices=["imagenet", "none"],
                         help="'none' matches the paper exactly (trained from scratch on SAR data). "
                              "'imagenet' (default) keeps this project's existing transfer-learning "
                              "choice — A/B both, this is a genuinely open question at this dataset size.")
    parser.add_argument("--despeckle", action="store_true")
    parser.add_argument("--loss", type=str, default="focal", choices=["dice_bce", "focal_tversky", "focal"])
    parser.add_argument("--focal-alpha", type=float, default=0.75)
    parser.add_argument("--focal-gamma", type=float, default=1.0,
                         help="1.0 default here (not train_unet.py's 2.0) — per project doc §5.5, "
                              "gamma=2.0 caused near-total loss collapse within ~100 batches at "
                              "this dataset's ~2% oil-pixel incidence. Confirmed 1.0 produces a "
                              "sane initial loss (~0.09-0.18 by hand-calculation, matches observed). "
                              "Raise cautiously and watch batch-0 loss before trusting a run.")
    parser.add_argument("--tversky-alpha", type=float, default=0.3)
    parser.add_argument("--tversky-beta", type=float, default=0.7)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--checkpoint-dir", type=str, default="checkpoints_wholescene")
    parser.add_argument("--no-amp", action="store_true")
    parser.add_argument("--resume", type=str, default=None,
                         help="Path to a unet_wholescene_last.pt (or _best.pt) checkpoint to fully "
                              "resume training from — same manifest/config, continuing epoch count, "
                              "optimizer, scheduler, and scaler state. Use this to keep training the "
                              "oil-only run past its last completed epoch, since it was still "
                              "improving when it stopped, not to switch manifests.")
    parser.add_argument("--init-checkpoint", type=str, default=None,
                         help="Path to a checkpoint to warm-start MODEL WEIGHTS ONLY from (fresh "
                              "optimizer/scheduler/epoch count) — the curriculum path. Use this to "
                              "fine-tune the mixed manifest starting from the oil-only checkpoint's "
                              "learned oil texture features, instead of from ImageNet weights, which "
                              "is what overfit/oscillated after epoch 6 in the first mixed run. "
                              "Ignored if --resume is also given.")
    parser.add_argument("--early-stop-patience", type=int, default=0,
                         help="Stop if val_oil_IoU doesn't improve for this many consecutive epochs. "
                              "0 (default) disables early stopping. Recommended: 6-8 for the mixed "
                              "manifest, given the observed peak-then-plateau pattern.")
    args = parser.parse_args()
    train(args)
