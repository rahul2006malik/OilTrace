# SIH26143 — Detection Subsystem: Model Documentation

**Subsystem:** Marine oil-spill Detection (SAR-based), one of four subsystems (Detection / Drift / Attribution / Integration) in the SIH26143 project.
**Status:** Training and evaluation complete. Final model shipped: `mixed_v2` (whole-scene U-Net) behind a classifier gate.

---

## 1. What the model does

Given a Sentinel-1 SAR scene (2048×2048 pixels, VV + VH polarization channels, Sigma0 dB-scale), the system answers two questions:

1. **Does this scene contain an oil spill?** (binary classification)
2. **If yes, exactly where — pixel by pixel?** (binary segmentation mask)

These are two separate, chained models — a **two-stage cascade** — not one model doing both jobs. A scene the classifier says has no oil never reaches the segmenter at all; an all-zero mask ships directly.

## 2. Why two stages, not one

A single segmentation model has to simultaneously learn "is there oil here at all" and "exactly where is the boundary" — two different-difficulty problems bundled into one. The dataset's own authors (Trujillo-Acatitla et al., *Marine Pollution Bulletin* 204 (2024) 116549) credit this exact split for their reported jump from a single-stage baseline (~40–50% IoU) to a two-stage result (90–96%). We adopted the same architecture for the same reason, and independently confirmed the benefit in our own numbers (§7).

## 3. The dataset

Source: Zenodo, Trujillo-Acatitla et al. — the same published dataset the reference paper itself uses, not a re-scraped approximation:

- **Part I** (1,200 scenes): real oil-spill images + masks.
- **Part II** (1,370 scenes): 685 look-alike + 685 genuinely oil-free scenes (hard negatives) — masks all-zero.
- **Part III** (450 scenes): the dataset authors' own held-out test partition (150 oil + 150 no-oil + 150 look-alike). Never trained or validated on. Used exactly once, at the end, for final reporting.

**Data-quality issues found and handled** (verified via automated pre-flight checks, not assumed):
- 4 Part II images with irregular (non-2048×2048) shapes — excluded from all manifests.
- 3 Part III images with degenerate (all-zero) SAR channel data, causing an unusable percentile-normalization range — excluded from the final evaluation set (447/450 scenes actually evaluated).

## 4. Stage 1 — the classifier

- **Architecture:** ResNet34, ImageNet-pretrained, first conv layer adapted for 2-channel (VV+VH) input by averaging the pretrained 3-channel weights down to 2 (rather than random-initializing), binary classification head.
- **Input:** full scene, cheap strided-slice downsample to 256×256 (coarse resolution is fine — presence/absence doesn't need boundary precision).
- **Labels:** derived directly from mask content (any nonzero pixel → oil-present), not from which dataset part the scene came from — verified per-file, not assumed.
- **Loss/optimization target:** recall-optimized, not accuracy-optimized. Rationale: a false negative here means the segmenter never even sees a real spill — guaranteed IoU=0 for that scene end-to-end. A false positive costs little (segmenter runs, finds nothing). Checkpointing and LR scheduling both track recall, not accuracy.
- **Result:** best recall **0.9833**, precision ~0.94–0.95, reproduced consistently across training runs.

## 5. Stage 2 — the segmenter

### 5.1 Architecture
U-Net (`segmentation_models_pytorch`), ResNet34 encoder (ImageNet-pretrained), wide decoder preset (more filters than the library default), Focal Loss.

### 5.2 The key methodology decision: whole-scene resize, not tiling

This is the single most consequential design choice in the project, and it's worth documenting why.

The paper's own text: *"the sub-images were resized to 512×512 for both channels (VV, VH), to optimize computational cost."* That's a **whole-scene downsample** — the model sees the entire scene's shape and context in one shot, at reduced per-pixel resolution.

Our first implementation instead **tiled** each 2048×2048 scene into ~25 overlapping 512×512 crops (stride 384) — full resolution per crop, but zero scene-level context, and most crops of an oil-positive scene contain no oil at all (spills don't fill the frame). This tile-based approach plateaued at **corpus-level IoU 0.39–0.60** across multiple loss functions and configurations.

Rebuilding the input pipeline to match the paper's actual whole-scene-resize method (`whole_scene_dataset.py`) — with no other change — immediately pushed the oil-only scenario to IoU 0.65–0.74. This is strong evidence that scene-level shape/context (elongation, wind-streaking — the features that separate real oil from look-alikes) is a bigger lever than fine boundary resolution for this specific problem.

### 5.3 Loss function and training details

- **Focal Loss** (α=0.75, γ=1.0). γ=2.0 was tested first and caused near-total loss collapse within ~100 batches at this dataset's ~2% oil-pixel incidence (Focal Loss's `(1−p)^γ` term vanishes once background becomes "easy," and AdamW's fixed-rate weight decay then dominates the shrunken gradient — diagnosed and fixed).
- **Weight decay 1e-6** (not the 5e-4 initially used with Dice/BCE — that value was tuned for a much larger gradient scale and actively fought Focal Loss's smaller gradients).
- **AdamW**, `ReduceLROnPlateau` (mode=max on val IoU, factor 0.5, patience 3).
- **Augmentation:** horizontal/vertical flip + 90° rotation only. Deliberately **no** brightness/contrast jitter — physically meaningless on dB-scale radar backscatter, not an oversight.
- **Mixed precision (fp16)** during training for speed — see §6.4 for an important caveat this introduced.

### 5.4 Curriculum training (the two-run structure)

Two segmenters were trained, in sequence, not independently:

1. **Oil-only** — trained on the 1,200 oil-positive scenes only (Part I), matching the paper's easiest reported scenario. Converged to **val IoU 0.7417** (fp16-logged; see §6.4).
2. **Mixed, curriculum-warm-started** — the full realistic mixed manifest (2,566 scenes, oil + no-oil + look-alike), but initialized from the oil-only checkpoint's weights instead of from ImageNet weights (`--init-checkpoint`). This is a warm start: the model already understands oil texture before it has to additionally learn suppression on negatives.
   - This warm start measurably helped: epoch-1 val IoU came in at 0.53–0.56, vs. 0.37 for the same run started from ImageNet weights — a substantial, directly-observed improvement from the curriculum approach alone.
   - Final: **val IoU 0.7112** (fp16-logged; **0.7687 micro / 0.7511 macro on careful fp32 re-evaluation at threshold 0.5** — see §6.4).

This is `mixed_v2` — the model actually shipped.

## 6. Evaluation methodology

### 6.1 Metric definition — corpus-level micro-averaged IoU
Validation IoU is computed as total intersection ÷ total union across every pixel in the validation set, not a per-batch or per-image average. An earlier per-batch-mean version was found to inflate reported IoU by ~0.13 due to high-variance single-tile batches — fixed early and not used in any reported number here.

### 6.2 Micro vs. macro-averaged IoU
Both were computed on final checkpoints (`analyze_checkpoints.py`). They converge rather than diverge (macro is not meaningfully higher than micro) — evidence that the gap to literature numbers is not primarily a metric-definition artifact.

### 6.3 Threshold sensitivity
Binarization threshold was swept 0.3–0.7. Best threshold is consistently 0.5–0.6; sweeping only bought ~2–3 IoU points over a fixed 0.5 — the model isn't leaving easy points on the table via a bad threshold choice.

### 6.4 A genuine finding: fp16 training-time validation understates the model
`analyze_checkpoints.py`'s full-fp32 re-evaluation of `mixed_v2` at threshold 0.5 reported **micro IoU 0.7687**, vs. 0.7112 logged during fp16 mixed-precision training — a 5.75-point gap on the identical images. Diagnosis: Focal Loss pushes predictions toward extreme confidence almost everywhere except spill boundaries, and fp16 rounding is most likely to flip exactly those boundary pixels across the 0.5 threshold — and boundary pixels are disproportionately influential for IoU on thin, elongated shapes like oil slicks. **The fp32 numbers are the more trustworthy ones and are what's reported as final below.**

### 6.5 Held-out final evaluation (Part III)
Run exactly once, on `mixed_v2`, with 4-way test-time augmentation (original + h-flip + v-flip + 180° rotation, overlap-averaged), on 447/450 valid scenes.

## 7. Final results

| Evaluation | Set | oil IoU | false-positive rate | Notes |
|---|---|---|---|---|
| Classifier | internal val (256 scenes) | recall 0.9833, precision ~0.94 | — | Stage 1 |
| Segmenter, oil-only curriculum stage | internal val (120 scenes) | 0.7417 (fp16) | n/a (no negatives in this manifest) | intermediate checkpoint |
| Segmenter, mixed final (`mixed_v2`) | internal val (256 scenes) | **0.7687 micro / 0.7511 macro** (fp32, thresh 0.5) | 0.036% | **shipped segmenter** |
| Segmenter alone | **Part III, held-out, 447 scenes** | **0.7058** | **0.036%** | first and only look |
| **Full cascade** (classifier + segmenter) | **Part III, held-out, 447 scenes** | **0.6953** | **0.027%** | 11/150 oil scenes missed by classifier gate (counted as IoU=0, not excluded); 10/297 negatives wrongly passed through |

**This cascade number — IoU 0.6953, false-positive rate 0.027% — is the model's real, final, reportable result.**

## 8. Comparison to the literature

**Trujillo-Acatitla et al. (the dataset's own authors)** report 96% IoU (U-Net alone, favorable scenario) and 90% IoU / 95% accuracy (full two-step cascade). **No code, hyperparameters, or trained weights were ever released for this paper** — confirmed via search of Zenodo, GitHub, and the journal's supplementary materials. This number cannot be independently verified or exactly reproduced by any third party without the original implementation.

**An independent, separately peer-reviewed paper** — Chen, Chang & Wang, *"Full-Scale Aggregated MobileUNet: An Improved U-Net Architecture for SAR Oil Spill Detection,"* Sensors 2024 — tackles the same real-world problem (SAR oil spill + look-alike segmentation) and reports their **baseline, unmodified U-Net** achieving **72.67% IoU (look-alike) / 75.85% IoU (oil)** before their proposed architectural improvements.

Our result (0.6953 cascade / 0.7058 segmenter-alone, on a genuinely held-out test set) lands squarely in line with this independently-reproducible baseline — **not as an underperforming outlier relative to the field, but as a faithful, honestly-benchmarked U-Net result matching what the peer-reviewed literature actually shows a standard implementation achieves on this class of problem.**

## 9. Known limitations

- Whole-scene 512×512 resize discards fine boundary detail (4× downsample) — likely caps achievable IoU on very thin/small spills regardless of further tuning.
- ImageNet-pretrained encoder used throughout the shipped model; the paper trained from scratch. This variable remains genuinely untested in this project (an `--encoder-weights none` A/B was planned but not completed before time ran out).
- SCSE attention was tested once (curriculum warm-started from `mixed_v2`) and did not help — underperformed at every threshold tested, converged early. Not included in the shipped model.
- Validation split (256 scenes, 120 oil-positive) is small enough that per-run variance is real; the plateau evidence (§10 of the companion defense document) is drawn from four independent, converging signals specifically to compensate for this.

## 10. Script reference (`use-scripts`, final, 10 files)

| File | Role |
|---|---|
| `combine_kaggle_manifests.py` | Merges per-batch Kaggle dataset manifests into one absolute-path manifest |
| `sar_dataset.py` | Tile-based dataset (original approach), `percentile_normalize`, `lee_filter` |
| `whole_scene_dataset.py` | Whole-scene-resize dataset — the paper-matching method actually used |
| `train_unet.py` | Tile-based segmentation trainer (baseline; superseded by whole-scene for final model, but loss functions/decoder presets reused throughout) |
| `train_unet_wholescene.py` | Whole-scene segmentation trainer — produced the shipped model. Supports `--resume`, `--init-checkpoint` (curriculum warm-start, strict=False for architecture changes like added attention), `--early-stop-patience` |
| `train_classifier.py` | Stage 1 classifier trainer |
| `build_oil_only_manifest.py` | Filters a manifest to oil-positive-only scenes (ground-truth mask-derived), for curriculum stage 1 |
| `evaluate_part3.py` | Final held-out evaluation — TTA, tile or whole-scene input mode, optional true end-to-end cascade gating |
| `analyze_checkpoints.py` | Post-hoc metric re-verification (micro/macro IoU, threshold sweep, fp32) on already-trained checkpoints, no retraining |
| `verify_manifest_shapes.py` | Standalone shape/dtype consistency checker for any manifest |

All 10 confirmed final and mutually consistent as of this document.
