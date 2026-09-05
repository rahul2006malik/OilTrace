"""
SIH26143 — Detection subsystem
Stage 1 of the two-stage classify-then-segment cascade: a binary "does
this scene contain oil?" classifier, trained and evaluated INDEPENDENTLY
of train_unet.py's segmentation model.

WHY THIS EXISTS: the dataset's own authors (Trujillo-Acatitla et al.)
credit a two-stage pipeline for their headline 90-96% IoU, distinct from
a single-stage segmentation model's ~60%. The idea: a dedicated
segmentation model, trained and evaluated ONLY on scenes already known to
contain oil, doesn't have to simultaneously learn "is there oil here at
all" AND "where exactly is it" — conflating those two different-difficulty
tasks is a real tax on segmentation quality. This classifier is the gate;
train_unet.py remains the "where exactly" model, ideally retrained on
oil-positive images only once this stage is working.

TRAINING DATA IS FREE: every image in your existing manifests already has
an implicit binary label — does its mask contain any nonzero pixel? This
script derives labels directly from mask CONTENT (not from source_prefix,
which is a plausible-but-unverified shortcut) — no assumption risk, no
new download or labeling needed.

MUCH CHEAPER TO TRAIN than segmentation: one label per 2048x2048 SCENE,
not per 512x512 tile — an epoch here is ~2,300 forward passes instead of
~57,000. Expect a small fraction of a segmentation epoch's wall-clock time.

HONESTY NOTE about recall vs precision: in the full cascade, a false
NEGATIVE here (real oil scene classified as "no oil") means the
segmentation model never even sees it — guaranteed IoU=0 for that scene
end-to-end, no matter how good the segmenter is. A false POSITIVE costs
comparatively little (segmenter just runs on a scene with nothing to
find, likely outputs near-empty). This asymmetry means: optimize this
classifier for HIGH RECALL on the oil class, even at some cost to
precision/false-positive rate — don't just chase raw accuracy.

Usage (Kaggle notebook, after combining manifests same as train_unet.py):
    !python train_classifier.py \
        --manifest /kaggle/working/manifest_train_combined.csv \
        --epochs 10 --batch-size 16 \
        --checkpoint-dir /kaggle/working/checkpoints_classifier
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

import numpy as np
import tifffile
import torch
import torch.nn as nn
import torchvision.models as tvm
from torch.utils.data import Dataset, DataLoader

from sar_dataset import percentile_normalize, lee_filter

RANDOM_SEED = 42
CLASSIFY_SIZE = 256  # downsampled scene size — fine pixel detail isn't
                      # needed for presence/absence, only for the
                      # segmentation stage that runs afterward.


def derive_label(mask_path: str) -> int:
    """1 if the mask contains ANY oil pixel, 0 if genuinely all-zero.
    Reads full mask content rather than trusting source_prefix as a
    shortcut — verified directly, no assumption risk.
    """
    mask = tifffile.imread(mask_path)
    return int(np.any(mask != 0))


class SceneClassificationDataset(Dataset):
    """One item per FULL SCENE, downsampled — NOT tiled like the
    segmentation dataset. Coarse resolution is fine here; we only need
    "is there oil anywhere in this scene", not precise boundaries.
    """

    def __init__(self, rows: list[dict], augment: bool = False, despeckle: bool = False):
        self.rows = rows
        self.augment = augment
        self.despeckle = despeckle

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int):
        row = self.rows[idx]
        image = tifffile.imread(row["image_path"])
        if self.despeckle:
            image = lee_filter(image)
        image = percentile_normalize(image)

        # Cheap strided-slice downsample (no extra deps) — exact
        # anti-aliasing doesn't matter for coarse presence/absence signal.
        h, w = image.shape[:2]
        step_h = max(1, h // CLASSIFY_SIZE)
        step_w = max(1, w // CLASSIFY_SIZE)
        small = image[::step_h, ::step_w, :][:CLASSIFY_SIZE, :CLASSIFY_SIZE, :]
        if small.shape[0] != CLASSIFY_SIZE or small.shape[1] != CLASSIFY_SIZE:
            padded = np.zeros((CLASSIFY_SIZE, CLASSIFY_SIZE, small.shape[2]), dtype=np.float32)
            padded[:small.shape[0], :small.shape[1], :] = small
            small = padded

        if self.augment:
            if random.random() < 0.5:
                small = np.flip(small, axis=0)
            if random.random() < 0.5:
                small = np.flip(small, axis=1)
            k = random.randint(0, 3)
            if k:
                small = np.rot90(small, k=k, axes=(0, 1))

        small = np.transpose(small, (2, 0, 1)).copy()
        label = int(row["label"])
        return torch.from_numpy(small).float(), torch.tensor([label], dtype=torch.float32)


def build_classifier() -> nn.Module:
    """ResNet34 (same family as the segmentation encoder, for consistency),
    modified for 2-channel VV+VH input, with a binary classification head.
    """
    model = tvm.resnet34(weights=tvm.ResNet34_Weights.IMAGENET1K_V1)
    old_conv = model.conv1
    new_conv = nn.Conv2d(2, old_conv.out_channels, kernel_size=old_conv.kernel_size,
                          stride=old_conv.stride, padding=old_conv.padding, bias=False)
    with torch.no_grad():
        # Average the pretrained 3-channel weights down to 2 channels
        # instead of random-initializing this layer — starts from
        # something sensible rather than pure noise.
        avg_weight = old_conv.weight.mean(dim=1, keepdim=True)  # (out_ch, 1, k, k)
        new_conv.weight.copy_(avg_weight.repeat(1, 2, 1, 1))
    model.conv1 = new_conv
    model.fc = nn.Linear(model.fc.in_features, 1)  # binary logit
    return model


def load_manifest_with_labels(manifest_csv: str) -> list[dict]:
    with open(manifest_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"Deriving binary oil-presence labels from mask content for {len(rows)} images...")
    for i, row in enumerate(rows):
        row["label"] = derive_label(row["mask_path"])
        if (i + 1) % 500 == 0 or (i + 1) == len(rows):
            print(f"  {i + 1}/{len(rows)} labeled...")
    n_pos = sum(r["label"] for r in rows)
    print(f"{n_pos}/{len(rows)} images contain oil ({n_pos/len(rows)*100:.1f}%), "
          f"{len(rows)-n_pos} do not.")
    return rows


def split_rows(rows: list[dict], val_fraction: float, seed: int):
    """Stratified by label so val set has both classes represented
    proportionally — same reasoning as train_unet.py's stratified split.
    """
    rng = random.Random(seed)
    pos = [r for r in rows if r["label"] == 1]
    neg = [r for r in rows if r["label"] == 0]
    rng.shuffle(pos)
    rng.shuffle(neg)
    n_val_pos = max(1, int(len(pos) * val_fraction))
    n_val_neg = max(1, int(len(neg) * val_fraction))
    val_rows = pos[:n_val_pos] + neg[:n_val_neg]
    train_rows = pos[n_val_pos:] + neg[n_val_neg:]
    rng.shuffle(train_rows)
    rng.shuffle(val_rows)
    return train_rows, val_rows


def train(args):
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    torch.manual_seed(RANDOM_SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    ckpt_dir = Path(args.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    rows = load_manifest_with_labels(args.manifest)
    train_rows, val_rows = split_rows(rows, val_fraction=0.1, seed=RANDOM_SEED)
    print(f"Split: {len(train_rows)} train / {len(val_rows)} val")

    train_ds = SceneClassificationDataset(train_rows, augment=True, despeckle=args.despeckle)
    val_ds = SceneClassificationDataset(val_rows, augment=False, despeckle=args.despeckle)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                               num_workers=args.num_workers, pin_memory=(device.type == "cuda"))
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                             num_workers=args.num_workers, pin_memory=(device.type == "cuda"))

    model = build_classifier().to(device)
    n_gpus = torch.cuda.device_count() if device.type == "cuda" else 0
    if n_gpus > 1:
        print(f"{n_gpus} GPUs visible — wrapping in nn.DataParallel.")
        model = nn.DataParallel(model)
    raw_model = model.module if isinstance(model, nn.DataParallel) else model

    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)

    best_val_recall = -1.0
    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
        avg_loss = running_loss / len(train_loader)

        model.eval()
        correct, total = 0, 0
        tp = fp = fn = tn = 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                logits = model(images)
                preds = (torch.sigmoid(logits) > 0.5).float()
                correct += (preds == labels).sum().item()
                total += labels.numel()
                tp += int(((preds == 1) & (labels == 1)).sum().item())
                fp += int(((preds == 1) & (labels == 0)).sum().item())
                fn += int(((preds == 0) & (labels == 1)).sum().item())
                tn += int(((preds == 0) & (labels == 0)).sum().item())

        val_acc = correct / max(total, 1)
        recall = tp / max(tp + fn, 1)      # of real oil scenes, how many caught
        precision = tp / max(tp + fp, 1)
        print(f"=== Epoch {epoch}: train_loss={avg_loss:.4f}, val_acc={val_acc:.4f}, "
              f"recall(oil caught)={recall:.4f}, precision={precision:.4f}, "
              f"tp={tp} fp={fp} fn={fn} tn={tn} ===")

        scheduler.step(recall)  # optimize the schedule around recall, not accuracy — see module docstring
        if recall > best_val_recall:
            best_val_recall = recall
            torch.save({
                "model_state_dict": raw_model.state_dict(),
                "val_acc": val_acc,
                "recall": recall,
                "precision": precision,
            }, ckpt_dir / "classifier_best.pt")
            print(f"New best recall={recall:.4f} (val_acc={val_acc:.4f}) — saved.")

    print(f"\nTraining complete. Best recall={best_val_recall:.4f}")
    print("If recall is under ~0.95, consider lowering the classification "
          "threshold below 0.5 at inference time (see cascade_predict below), "
          "even at some cost to precision — a missed true oil scene costs the "
          "whole cascade everything for that scene; a spurious classification "
          "just means the segmenter runs and likely finds little.")


@torch.no_grad()
def cascade_predict(classifier_ckpt: str, segmenter_ckpt: str, image_path: str,
                     device: torch.device, classify_threshold: float = 0.5):
    """Reference implementation of the full two-stage inference — classify
    first, only run the (expensive, tile-by-tile) segmentation model if the
    classifier says oil is present. Otherwise return an all-zero mask
    directly, skipping segmentation entirely.

    This is the honest, END-TO-END path — unlike the paper's conditional
    number, this reflects what actually happens including classifier
    mistakes: a false negative here means an all-zero mask ships for a
    real oil scene, exactly as it would in production.
    """
    import segmentation_models_pytorch as smp
    from evaluate_part3 import predict_full_scene  # reuses the TTA + overlap-averaged inference already built

    classifier = build_classifier().to(device)
    ckpt = torch.load(classifier_ckpt, map_location=device)
    classifier.load_state_dict(ckpt["model_state_dict"])
    classifier.eval()

    ds_helper = SceneClassificationDataset([{"image_path": image_path, "label": 0}], augment=False)
    image_small, _ = ds_helper[0]
    image_small = image_small.unsqueeze(0).to(device)
    prob_oil = torch.sigmoid(classifier(image_small)).item()

    if prob_oil < classify_threshold:
        import tifffile as _tifffile
        scene = _tifffile.imread(image_path)
        return np.zeros(scene.shape[:2], dtype=np.float32), prob_oil, False  # skip segmentation

    segmenter = smp.Unet(encoder_name="resnet34", encoder_weights=None, in_channels=2, classes=1)
    seg_ckpt = torch.load(segmenter_ckpt, map_location=device)
    segmenter.load_state_dict(seg_ckpt["model_state_dict"])
    segmenter.to(device).eval()

    prob_map = predict_full_scene(segmenter, image_path, device)
    return prob_map, prob_oil, True  # segmentation actually ran


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--checkpoint-dir", type=str, default="checkpoints_classifier")
    parser.add_argument("--despeckle", action="store_true")
    args = parser.parse_args()
    train(args)
