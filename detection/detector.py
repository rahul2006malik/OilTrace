"""
detection/detector.py — SIH26143 Detection subsystem

Production two-stage cascade inference engine: wraps the trained Stage 1
classifier (oil/no-oil gate) and Stage 2 whole-scene U-Net segmenter
checkpoints described in Detection_Model_Documentation.md (`mixed_v2`,
IoU 0.6953 cascade / FP rate 0.027% on Part III), and turns a raw
Sentinel-1 SAR scene into schemas.md-compliant output.

DESIGN NOTE — read before touching model-loading code in here:
This module deliberately REUSES `use-scripts/evaluate_part3.py`'s
`load_model` / `predict_full_scene_wholescene` and `train_classifier.py`'s
`build_classifier`, rather than reconstructing the segmenter/classifier
architecture inline a second time. Detection_Model_Documentation.md §6.4
and §7 describe real time spent diagnosing a bug caused by exactly this
kind of duplication (fp16-vs-fp32 mismatch, decoder-width/attention
mismatches). A second, independently-written `smp.Unet(...)` construction
in this file would be a second place that can silently drift out of sync
with whatever the shipped checkpoint was actually trained with — that's
not a hypothetical, it's the specific failure class this project already
paid down once. If you need different inference behaviour, change it in
evaluate_part3.py (the single, already-tested source of truth for
loading/TTA), not here.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
import tifffile
import torch

# --- Dynamic path resolution (matches use-scripts/run_cascade.py) --------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
USE_SCRIPTS_DIR = PROJECT_ROOT / "use-scripts"
CHECKPOINTS_DIR = PROJECT_ROOT / "checkpoints"

for _p in (USE_SCRIPTS_DIR, PROJECT_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from evaluate_part3 import (  # noqa: E402  (import after sys.path setup, deliberate)
    _classify_scene,
    load_model,
    predict_full_scene_wholescene,
)
from train_classifier import build_classifier  # noqa: E402

from .postprocess import mask_to_geojson, try_read_geotiff_georeference

# --- Shipped model configuration ------------------------------------------
# Hardcoded, not guessed, per Detection_Model_Documentation.md §5/§7
# ("mixed_v2", wide decoder, no attention, whole-scene input mode).
# Loading the wrong decoder width/attention against these specific
# checkpoints fails loudly (state_dict shape mismatch) or silently produces
# nonsense (input_mode mismatch) — see the explicit check in __init__.
_SHIPPED_DECODER_WIDTH = "wide"
_SHIPPED_DECODER_ATTENTION = "none"
_SHIPPED_INPUT_MODE = "whole_scene"

DEFAULT_CLASSIFIER_CKPT = CHECKPOINTS_DIR / "classifier_best.pt"
DEFAULT_SEGMENTER_CKPT = CHECKPOINTS_DIR / "unet_wholescene_best.pt"


def _resolve_path(path: Union[str, Path]) -> Path:
    """Relative paths resolve against PROJECT_ROOT, not the caller's CWD —
    per task spec, so this module behaves the same whether invoked from a
    notebook, a test script, or a FastAPI process with an arbitrary CWD."""
    p = Path(path)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


class OilSpillDetector:
    """Two-stage (classify -> segment) SAR oil-spill cascade, production wrapper.

    Loads both checkpoints once at construction time; call `.predict()` per
    scene thereafter. Not thread-safe for concurrent `.predict()` calls on
    the SAME instance (shared CUDA/model state) — instantiate one detector
    per worker process if you need concurrency, don't share one across
    threads.
    """

    def __init__(
        self,
        classifier_path: Union[str, Path] = DEFAULT_CLASSIFIER_CKPT,
        segmenter_path: Union[str, Path] = DEFAULT_SEGMENTER_CKPT,
        device: Optional[str] = None,
    ):
        self.classifier_path = _resolve_path(classifier_path)
        self.segmenter_path = _resolve_path(segmenter_path)

        if not self.classifier_path.exists():
            raise FileNotFoundError(f"Classifier checkpoint not found: {self.classifier_path}")
        if not self.segmenter_path.exists():
            raise FileNotFoundError(f"Segmenter checkpoint not found: {self.segmenter_path}")

        self.device = torch.device(
            device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
        )
        print(f"[OilSpillDetector] device={self.device.type}")

        # --- Stage 1: classifier ---
        self.classifier = build_classifier().to(self.device)
        c_ckpt = torch.load(self.classifier_path, map_location=self.device)
        self.classifier.load_state_dict(c_ckpt["model_state_dict"])
        self.classifier.eval()
        self.classifier_recall = c_ckpt.get("recall")
        self.classifier_precision = c_ckpt.get("precision")

        # --- Stage 2: segmenter ---
        self.segmenter, ckpt_input_mode = load_model(
            str(self.segmenter_path),
            self.device,
            decoder_width=_SHIPPED_DECODER_WIDTH,
            decoder_attention=_SHIPPED_DECODER_ATTENTION,
        )
        if ckpt_input_mode != _SHIPPED_INPUT_MODE:
            # Hard error, not evaluate_part3.py's softer warning-and-proceed:
            # that script is run interactively by a human who can read the
            # console; this class gets called from FastAPI/test code with
            # nobody watching stdout. Silently running a tile-trained
            # checkpoint through the whole-scene prediction path produces a
            # confident-looking but meaningless probability map.
            raise ValueError(
                f"Segmenter checkpoint at {self.segmenter_path} recorded "
                f"input_mode='{ckpt_input_mode}', but OilSpillDetector is hardcoded for "
                f"the shipped whole-scene model (input_mode='{_SHIPPED_INPUT_MODE}', "
                f"Detection_Model_Documentation.md §5). Point segmenter_path at the "
                f"correct checkpoint."
            )

    def predict(
        self,
        image_path: Union[str, Path],
        classify_threshold: float = 0.5,
        segment_threshold: float = 0.5,
        geo_bounds: Optional[Tuple[float, float, float, float]] = None,
        center_lonlat: Optional[Tuple[float, float]] = None,
        source_scene_id: Optional[str] = None,
        detected_at: Optional[str] = None,
        spill_id: Optional[str] = None,
    ) -> dict:
        """Run the full two-stage cascade on one SAR scene.

        Returns:
            {
              "has_oil": bool,
              "oil_confidence": float,       # combined score once a polygon
                                              # exists; classifier's raw P(oil)
                                              # if Stage 1 gated out.
              "prob_map": np.ndarray | None, # None iff Stage 1 gated out —
                                              # this is the concrete signal
                                              # that Stage 2 never ran.
              "geojson": dict | None,        # schemas.md slick_detection.geojson,
                                              # or None (no oil / no surviving blob).
              "execution_time_seconds": float,
            }
        """
        start = time.perf_counter()
        image_path_str = str(image_path)

        # --- Stage 1: classification gate --------------------------------
        classify_prob = _classify_scene(self.classifier, image_path_str, self.device)
        oil_detected = classify_prob >= classify_threshold

        if not oil_detected:
            return {
                "has_oil": False,
                "oil_confidence": float(classify_prob),
                "prob_map": None,
                "geojson": None,
                "execution_time_seconds": time.perf_counter() - start,
            }

        # --- Stage 2: whole-scene segmentation, 4-way TTA ------------------
        prob_map = predict_full_scene_wholescene(self.segmenter, image_path_str, self.device)
        prob_map = prob_map.astype(np.float32)

        # Deliberately a FRESH, RAW (non-normalized) read of the TIFF here —
        # not a reuse of whatever normalized array fed the model. The
        # thickness-class proxy needs actual dB backscatter values;
        # percentile-normalized [0,1] model input would make the dB
        # thresholds in postprocess.py meaningless. Yes, this means the
        # file gets decoded from disk more than once per call (classifier,
        # segmenter, and here) — acceptable for single-scene interactive/demo
        # inference, not something to "optimize" by sharing a normalized
        # array across stages without checking what each stage actually needs.
        raw_scene = tifffile.imread(image_path_str)
        if raw_scene.ndim == 2:
            raw_scene = raw_scene[:, :, None]

        resolved_source_scene_id = source_scene_id or Path(image_path_str).stem
        geotiff_transform = try_read_geotiff_georeference(image_path_str)

        geojson = mask_to_geojson(
            prob_map=prob_map,
            raw_scene=raw_scene,
            classify_confidence=classify_prob,
            threshold=segment_threshold,
            geo_bounds=geo_bounds,
            center_lonlat=center_lonlat,
            geotiff_transform=geotiff_transform,
            spill_id=spill_id,
            detected_at=detected_at,
            source_scene_id=resolved_source_scene_id,
            lookalike_suppressed=False,  # see postprocess.py module docstring, note (1)
        )

        final_confidence = float(geojson["oil_confidence"]) if geojson is not None else float(classify_prob)

        return {
            "has_oil": geojson is not None,
            "oil_confidence": final_confidence,
            "prob_map": prob_map,
            "geojson": geojson,
            "execution_time_seconds": time.perf_counter() - start,
        }
