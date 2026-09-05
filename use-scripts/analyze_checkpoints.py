"""
SIH26143 — Detection subsystem
analyze_checkpoints.py — recomputes validation metrics on ALREADY-TRAINED
whole-scene checkpoints with no retraining, to check whether part of the
gap to the paper's reported 90-96% is a METRIC DEFINITION difference
rather than a model-quality difference.

WHY THIS MATTERS: train_unet_wholescene.py's validation loop reports
corpus-level MICRO-averaged IoU (total intersection / total union across
every pixel in the val set) at a FIXED 0.5 threshold. This is a
methodologically rigorous choice (see project doc §5.6's history of the
noisier per-batch-mean metric bug it replaced) but it is not necessarily
what any given paper reports. Two common alternatives that are typically
HIGHER on the exact same predictions:
  - MACRO-averaged IoU: compute IoU per scene, then average those numbers.
    Small/easy scenes contribute equally to easy AND hard scenes, rather
    than being diluted by pixel count the way micro-averaging does.
  - Best-threshold IoU: sweeping the binarization threshold (evaluate_
    part3.py already does this for the final Part III report) instead of
    assuming 0.5 is optimal.

This script reports BOTH metrics across a threshold sweep, on the SAME
validation split train_unet_wholescene.py used (same seed, same
stratified-by-source_prefix split logic, reused directly via import) so
the numbers are a fair like-for-like comparison against what you already
have — not a new, cherry-picked split.

HONESTY NOTE: if macro-averaged IoU comes back meaningfully higher than
the corpus-micro number you've been tracking, that's a genuinely valid
number to ALSO report (many papers use it) — but keep reporting corpus-
micro too, and be explicit about which one is which in front of judges.
Silently switching to whichever number is bigger without saying so is the
kind of thing that erodes trust in a technical Q&A far more than a lower,
honestly-labeled number would.

Usage (Kaggle, after training — works on CPU too, it's inference-only,
no need to hold a GPU for this):
    !python analyze_checkpoints.py \
        --manifest /kaggle/working/manifest_oil_only.csv \
        --checkpoint /kaggle/working/checkpoints_wholescene_oilonly/unet_wholescene_best.pt \
        --decoder-width wide

    !python analyze_checkpoints.py \
        --manifest /kaggle/working/manifest_train_combined.csv \
        --checkpoint /kaggle/working/checkpoints_wholescene_mixed_v2/unet_wholescene_best.pt \
        --decoder-width wide
"""

from __future__ import annotations

import argparse

import numpy as np
import segmentation_models_pytorch as smp
import torch
from torch.utils.data import DataLoader

from train_unet_wholescene import VAL_FRACTION, RANDOM_SEED, split_rows_by_image
from train_unet import DECODER_WIDTH_PRESETS
from whole_scene_dataset import SARWholeSceneDataset, load_wholescene_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True,
                         help="Same manifest the checkpoint was TRAINED on (oil-only or mixed) — "
                              "needed to reconstruct the identical val split.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--decoder-width", default="wide", choices=list(DECODER_WIDTH_PRESETS.keys()))
    parser.add_argument("--decoder-attention", default="none", choices=["none", "scse"])
    parser.add_argument("--despeckle", action="store_true")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--thresholds", type=str, default="0.3,0.4,0.5,0.6,0.7")
    args = parser.parse_args()
    thresholds = [float(t) for t in args.thresholds.split(",")]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    rows = load_wholescene_manifest(args.manifest)
    _, val_rows = split_rows_by_image(rows, VAL_FRACTION, RANDOM_SEED)
    val_ds = SARWholeSceneDataset(val_rows, augment=False, despeckle=args.despeckle)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=2)

    model = smp.Unet(
        encoder_name="resnet34", encoder_weights=None, in_channels=2, classes=1,
        decoder_channels=DECODER_WIDTH_PRESETS[args.decoder_width],
        decoder_attention_type=(args.decoder_attention if args.decoder_attention != "none" else None),
    ).to(device)
    ckpt = torch.load(args.checkpoint, map_location=device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    print(f"Loaded {args.checkpoint} (epoch={ckpt.get('epoch')}, "
          f"its own recorded val_oil_iou={ckpt.get('val_oil_iou')})\n")

    # Run inference ONCE, cache raw probability maps, sweep thresholds cheaply.
    all_probs, all_targets = [], []
    with torch.no_grad():
        for images, masks in val_loader:
            images = images.to(device)
            probs = torch.sigmoid(model(images)).cpu().numpy()  # (B,1,512,512)
            targets = (masks.numpy() > 0.5).astype(np.float32)  # threshold soft-resized GT once, same as training
            for b in range(probs.shape[0]):
                all_probs.append(probs[b, 0])
                all_targets.append(targets[b, 0])
    print(f"Evaluated {len(all_probs)} validation scenes.\n")

    print(f"{'threshold':>10} | {'micro IoU':>10} | {'macro IoU':>10} | {'macro std':>10} | n_oil_scenes")
    print("-" * 70)
    for thresh in thresholds:
        total_inter, total_union = 0.0, 0.0
        per_scene_ious = []
        for prob, target in zip(all_probs, all_targets):
            pred = (prob > thresh).astype(np.float32)
            inter = float((pred * target).sum())
            union = float(((pred + target) > 0).sum())
            has_oil = target.sum() > 0
            if has_oil:
                total_inter += inter
                total_union += union
                per_scene_ious.append(inter / union if union > 0 else 0.0)

        micro_iou = total_inter / max(total_union, 1e-6)
        macro_iou = float(np.mean(per_scene_ious)) if per_scene_ious else float("nan")
        macro_std = float(np.std(per_scene_ious)) if per_scene_ious else float("nan")
        print(f"{thresh:>10.2f} | {micro_iou:>10.4f} | {macro_iou:>10.4f} | {macro_std:>10.4f} | {len(per_scene_ious)}")

    print("\nmicro IoU = same metric train_unet_wholescene.py reports (total intersection / total union).")
    print("macro IoU = per-scene IoU averaged across scenes — often closer to what papers report.")
    print("If macro is notably higher than micro at the same threshold, some of the gap to literature")
    print("numbers is a metric-definition difference, not purely a model-quality difference — worth")
    print("disclosing both when reporting results, not just switching to the higher one silently.")


if __name__ == "__main__":
    main()
