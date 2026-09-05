# OilTrace — Satellite SAR Marine Oil Spill Detection & Attribution

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-ee4c2c.svg)](https://pytorch.org/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-success.svg)]()

> **SIH26143 — NTRO Problem Statement:** Automated Detection, Drift Hindcasting, and AIS Attribution of Marine Oil Spills from Satellite SAR Imagery.

---

## 🎯 Headline Performance Metrics

Evaluated **once** on the authors' strictly held-out **447-scene test partition (Part III)** — never trained, validated, or tuned against:

| Metric | Full Two-Stage Cascade (Shipped) | Segmenter Alone (Upper Bound) | Classifier Gate Alone |
| :--- | :--- | :--- | :--- |
| **Oil Spill IoU** | **0.6953 (69.53%)** | **0.7058 (70.58%)** | N/A (Classification) |
| **False-Positive Rate** | **0.027% (0.00027)** | **0.036% (0.00036)** | Precision: 94.40% |
| **Spill Detection Recall** | Evaluated end-to-end | N/A (Ungated) | **98.33%** |
| **Evaluation Set** | 447 scenes (150 oil + 297 negatives) | 447 scenes | 256 internal val scenes |

*Key Takeaway: The cascade gate eliminates look-alike and clear-water false alarms, reducing false positives down to 0.027% while preserving near-ceiling IoU (69.53% vs 70.58%). Missed real spills (11/150) are honestly counted as IoU = 0 in the end-to-end figure.*

---

## 📖 Subsystem Documentation & Defense Guides

- 📘 **[Detection Model Documentation](docs/Detection_Model_Documentation.md)**: Full architecture specification, dataset splits, curriculum training protocol, Focal Loss mechanics, fp16 vs fp32 validation findings, and ablation analysis.
- 🛡️ **[Defending Model Accuracy — SIH Judge Prep](docs/Defending_Model_Accuracy.md)**: Straight-talking pitch defense guide addressing benchmark realism, independent Sensor paper comparisons (72.6–75.8% baseline), and technical trade-offs.
- 📐 **[Data Schema Contracts](schemas.md)**: Input/Output GeoJSON contracts bridging Detection (slick_detection.geojson), Drift (origin_ensemble.json), and Attribution (ttribution_result.json).

---

## 🏗️ Repository Architecture

`	ext
C:\WORK\OilTrace\
├── checkpoints\                     # Production deployment weights
│   ├── classifier_best.pt           # Stage 1: ResNet34 binary classifier gate
│   └── unet_wholescene_best.pt      # Stage 2: U-Net ResNet34 wide-decoder segmenter (mixed_v2)
├── checkpoints_archive\             # Intermediate curriculum artifacts
│   └── unet_wholescene_oilonly_best.pt # Warm-start model trained on Part I (oil-only)
├── use-scripts\                     # Canonical model scripts
│   ├── analyze_checkpoints.py       # Threshold sweep & micro vs. macro IoU analysis
│   ├── build_oil_only_manifest.py   # Manifest filter for curriculum Stage 1
│   ├── combine_kaggle_manifests.py  # Stratified merger for Part I + Part II
│   ├── evaluate_part3.py            # Part III held-out evaluation runner (TTA + stitching)
│   ├── sar_dataset.py               # SAR tile dataset, Lee filtering & dB normalization
│   ├── train_classifier.py          # ResNet34 classifier trainer & cascade inference
│   ├── train_unet.py                # Tile-based U-Net trainer baseline
│   ├── train_unet_wholescene.py     # Whole-scene U-Net trainer with Focal Loss
│   ├── verify_manifest_shapes.py    # Preflight integrity checks for SAR scenes
│   └── whole_scene_dataset.py       # Whole-scene downsampling & augmentation loader
├── demo\                            # Verification and runnable CLI demo
│   ├── verify_checkpoints.py        # Smoke-test loader to verify checkpoint integrity
│   └── run_cascade.py               # Full two-stage CLI inference & visualizer
├── docs\                            # Architectural and technical documentation
├── reports\                         # Held-out Part III benchmark evaluation reports
│   ├── part3_report_cascade.json    # Full cascade benchmark report (IoU: 0.6953)
│   └── part3_report_segmenter_only.json # Ungated segmenter benchmark report (IoU: 0.7058)
├── requirements.txt                 # Clean Python environment dependencies
└── README.md
`

---

## ⚙️ Environment Setup

### 1. Prerequisites
- Python 3.10+ (Python 3.10, 3.11, 3.12, or 3.13)
- Windows, Linux, or macOS
- CUDA GPU is optional. If CUDA is not detected, PyTorch automatically falls back to CPU for inference (runs in ~1.5s per scene on CPU).

### 2. Installation
Create and activate a virtual environment:
`ash
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate
`

Install the dependencies:
`ash
pip install -r requirements.txt
`

---

## 🚀 Running the Model

### Step 1: Verify Model Checkpoints
Confirm both model weights are intact and loadable:
`ash
python demo/verify_checkpoints.py
`
*Expected Output:*
`	ext
classifier: OK, keys=['model_state_dict', 'val_acc', 'recall', 'precision']
segmenter: OK, keys=['epoch', 'model_state_dict', 'val_oil_iou', 'loss', 'input_mode']
`

### Step 2: Run Two-Stage Cascade Inference Demo
Run the end-to-end inference CLI on any Sentinel-1 SAR scene (TIFF format):

`ash
python demo/run_cascade.py \
    --image data/processed/part3/Images/Oil/00000.tif \
    --classifier-checkpoint checkpoints/classifier_best.pt \
    --segmenter-checkpoint checkpoints/unet_wholescene_best.pt \
    --output-dir demo/sample_output
`

#### Demo Output & Artifacts:
1. **Console Telemetry**: Reports Stage 1 classification probability, gate decision, Stage 2 segmentation range, and total slick pixel area.
2. **Probability Array (.npy)**: Native-resolution (2048×2048) float32 probability array [0.0, 1.0].
3. **Visual Result (.png)**: High-contrast SAR backscatter with a diagnostic banner and segmented oil slick overlay contours.

---

## 🔬 How the Two-Stage Cascade Works

1. **Stage 1 — Classifier Gate (ResNet34)**
   - Pretrained ResNet34 adapted for 2-channel SAR (VV, VH backscatter).
   - Downsamples whole scene to 256×256.
   - **Tuned for Recall (98.33%)**: A missed spill causes the entire pipeline to fail silently; false alarms merely invoke the segmenter.
   - If (\text{oil}) < 0.50$, an all-zero mask is output immediately, saving compute and preventing false positives on look-alikes.

2. **Stage 2 — Segmenter (U-Net Wide Decoder)**
   - ResNet34 backbone with a **wide decoder** ((512, 256, 128, 64, 32)).
   - Whole-scene context ingestion matching Trujillo-Acatitla et al. (512×512 resize + 4-way Test-Time Augmentation).
   - Trained via **Curriculum Learning**: Stage 1 warm-started on 1,200 oil-only scenes (Part I), Stage 2 fine-tuned with Focal Loss ($\alpha=0.75, \gamma=1.0$) on 2,566 mixed scenes (Part I + Part II hard look-alikes).

---

## 🛰️ Integration with Drift & Attribution
When oil is detected, the binary mask is vectorized to GeoJSON complying with [schemas.md](schemas.md):
- **Detection -> Drift (slick_detection.geojson)**: Feeds spill centroid [lon, lat], estimated area rea_km2, and geometry to OpenDrift backward hindcasting.
- **Drift -> Attribution (origin_ensemble.json)**: Computes reverse-trajectory probability cones (50%, 75%, 90%).
- **Attribution (ttribution_result.json)**: Intersects spatio-temporal cones with Global Fishing Watch (GFW) & AISStream feeds to rank dark/AIS-transmitting vessels with suspicion scores.
