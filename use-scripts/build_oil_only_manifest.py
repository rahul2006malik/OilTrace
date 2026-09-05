"""
SIH26143 — Detection subsystem
build_oil_only_manifest.py — filters a combined manifest down to scenes
that actually contain oil, so train_unet_wholescene.py (or train_unet.py)
can be retrained on an oil-only stage-2 set.

WHY THIS MATTERS: this is the "unclaimed upside" flagged in the handoff
doc, §6 and §7 step 8. The paper's own headline numbers (96% IoU U-Net
alone vs 90% IoU for the full two-step CNN+U-Net framework) only make
sense if the segmenter's best-case number was measured on a favorable,
oil-only-or-near-oil-only scenario — a segmenter that never has to also
decide "is there oil here at all" can spend its whole capacity on "where
exactly is the boundary." Mixing in Part II's all-zero-mask look-alikes
and no-oil negatives (which is what train_unet.py currently does when fed
a combined Part I + Part II manifest) makes the segmentation task harder
than the paper's best-reported config, not equivalent to it.

This does NOT throw away Part II — it's still valuable for training/
sanity-checking the classifier (train_classifier.py) and for computing an
honest end-to-end cascade IoU later in evaluate_part3.py. It just isn't
useful for THIS segmenter-only training run, exactly the same way the
paper describes running the U-Net stage on oil-containing scenes as its
own scenario, separate from the "realistic" mixed scenario.

LABELS ARE FREE, same reasoning as train_classifier.py: every mask
already encodes ground truth presence/absence, no new annotation needed.
Uses actual mask content, not source_prefix, as the source of truth —
source_prefix is a plausible-but-unverified shortcut (e.g. if Part I ever
grows a genuinely-empty scene, or a manifest gets hand-edited).

Usage (Kaggle, after combine_kaggle_manifests.py has already produced a
combined manifest):
    !python build_oil_only_manifest.py \
        --manifest /kaggle/working/manifest_train_combined.csv \
        --output /kaggle/working/manifest_oil_only.csv

Optional: reuse an already-trained classifier's predicted labels instead
of ground-truth mask content, via --classifier-checkpoint, so the
segmenter is trained on exactly the distribution it will see at cascade
inference time (scenes the classifier THINKS contain oil, which is not
identical to scenes that truly do — the classifier has ~1.7% false
negatives and some false positives at recall=0.9833). This is a closer
match to production but introduces classifier-error noise into training
labels; ground-truth mask-derived filtering (the default) is the cleaner
starting point and what the paper's staged-scenario description implies.
"""

from __future__ import annotations

import argparse
import csv

import numpy as np
import tifffile


def derive_label(mask_path: str) -> int:
    """1 if the mask contains ANY oil pixel, 0 if genuinely all-zero.
    Same logic as train_classifier.py's derive_label — kept independent
    here (not imported) so this script has zero dependency on torch/
    torchvision and can run fast on a CPU-only Kaggle session if needed.
    """
    mask = tifffile.imread(mask_path)
    return int(np.any(mask != 0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True,
                         help="Combined manifest CSV (id,image_path,mask_path[,source_prefix]).")
    parser.add_argument("--output", required=True,
                         help="Where to write the oil-only-filtered manifest.")
    parser.add_argument("--classifier-checkpoint", type=str, default=None,
                         help="Optional: path to classifier_best.pt. If given, filters by the "
                              "CLASSIFIER's predicted label instead of ground-truth mask content "
                              "— matches production cascade distribution more closely, at the "
                              "cost of baking in the classifier's current false-negative/positive "
                              "behavior into what the segmenter trains on. Requires torch/torchvision.")
    parser.add_argument("--classify-threshold", type=float, default=0.5)
    args = parser.parse_args()

    with open(args.manifest, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or ["id", "image_path", "mask_path"]

    if args.classifier_checkpoint:
        # Lazy imports so the ground-truth path (default) never needs torch.
        import torch
        from train_classifier import SceneClassificationDataset, build_classifier

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = build_classifier().to(device)
        ckpt = torch.load(args.classifier_checkpoint, map_location=device)
        model.load_state_dict(ckpt["model_state_dict"])
        model.eval()
        print(f"Loaded classifier checkpoint (recall={ckpt.get('recall', 'n/a')}, "
              f"precision={ckpt.get('precision', 'n/a')}). Filtering by PREDICTED label "
              f"at threshold={args.classify_threshold}.")

        ds = SceneClassificationDataset(
            [{"image_path": r["image_path"], "label": 0} for r in rows], augment=False
        )
        kept = []
        with torch.no_grad():
            for i, row in enumerate(rows):
                image, _ = ds[i]
                image = image.unsqueeze(0).to(device)
                prob = torch.sigmoid(model(image)).item()
                if prob >= args.classify_threshold:
                    kept.append(row)
                if (i + 1) % 500 == 0 or (i + 1) == len(rows):
                    print(f"  classified {i + 1}/{len(rows)}...")
    else:
        print(f"Filtering by GROUND-TRUTH mask content for {len(rows)} images "
              f"(this is the paper-matching, cleaner-signal option)...")
        kept = []
        for i, row in enumerate(rows):
            if derive_label(row["mask_path"]) == 1:
                kept.append(row)
            if (i + 1) % 500 == 0 or (i + 1) == len(rows):
                print(f"  checked {i + 1}/{len(rows)}...")

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(kept)

    print(f"\nKept {len(kept)}/{len(rows)} images ({len(kept)/max(len(rows),1)*100:.1f}%) -> {args.output}")
    if len(kept) == len(rows):
        print("WARNING: kept 100% of rows — check that --manifest actually includes "
              "Part II no-oil/look-alike negatives (mixed manifest expected), "
              "otherwise this filter had nothing to remove and is a no-op.")


if __name__ == "__main__":
    main()
