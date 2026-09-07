"""
detection/test_detection_pipeline.py — SIH26143 Detection subsystem

Standalone, no-pytest-required verification script. Run this after any
change to detector.py or postprocess.py, and before handing
`slick_detection.geojson` output to the Drift subsystem — it's the
concrete proof that this module's output actually satisfies schemas.md,
not just that it runs without raising.

Usage:
    python detection/test_detection_pipeline.py

Requires real checkpoints at checkpoints/classifier_best.pt and
checkpoints/unet_wholescene_best.pt, and the two Part III sample scenes
below to exist on disk. This is intentional — it is an integration test
against real model weights and real data, not a mocked unit test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from detection import OilSpillDetector  # noqa: E402

try:
    import pytest

    @pytest.fixture(scope="module")
    def detector() -> OilSpillDetector:
        return OilSpillDetector()
except ImportError:
    pass


POSITIVE_SAMPLE = PROJECT_ROOT / "data" / "processed" / "part3" / "Images" / "Oil" / "00000.tif"
NEGATIVE_SAMPLE = PROJECT_ROOT / "data" / "processed" / "part3" / "Images" / "No oil" / "00000.tif"
OUTPUT_GEOJSON = PROJECT_ROOT / "detection" / "sample_slick_detection.geojson"

# Exact field set from schemas.md §1 (slick_detection.geojson). Kept as an
# explicit literal set (not imported from a schema library) so this file
# has zero extra dependencies — if schemas.md changes, update this by hand
# and treat that as the schema-change protocol's "ping affected threads"
# step (Orchestration Playbook §6) for the Detection thread.
REQUIRED_KEYS = {
    "spill_id",
    "detected_at",
    "geometry",
    "centroid",
    "area_km2",
    "elongation_ratio",
    "oil_confidence",
    "lookalike_suppressed",
    "thickness_class",
    "source_scene_id",
    "data_provenance",
}


def _check_missing_inputs() -> list[str]:
    problems = []
    for label, path in [
        ("positive sample scene", POSITIVE_SAMPLE),
        ("negative sample scene", NEGATIVE_SAMPLE),
    ]:
        if not path.exists():
            problems.append(f"Missing {label}: {path}")
    return problems


def test_positive_sample(detector: OilSpillDetector) -> dict:
    print(f"\n[TEST] Positive sample: {POSITIVE_SAMPLE}")
    result = detector.predict(str(POSITIVE_SAMPLE))

    assert result["has_oil"] is True, (
        f"Expected has_oil=True on a known-positive scene, got {result['has_oil']} "
        f"(oil_confidence={result['oil_confidence']:.4f}). If this genuinely fails, "
        f"that's a real regression to investigate — don't loosen this assertion "
        f"to make the test pass."
    )
    geojson = result["geojson"]
    assert geojson is not None, "has_oil=True but geojson is None — inconsistent detector state."

    missing = REQUIRED_KEYS - geojson.keys()
    assert not missing, f"geojson is missing required schemas.md fields: {sorted(missing)}"

    extra = geojson.keys() - REQUIRED_KEYS
    if extra:
        print(f"  NOTE: geojson has extra, non-schema fields (harmless, flagging anyway): {sorted(extra)}")

    assert geojson["thickness_class"] in {"sheen", "thin", "thick"}, (
        f"thickness_class={geojson['thickness_class']!r} is not a valid schema enum value"
    )
    assert geojson["data_provenance"] in {"real_detector", "real_uploaded_fixture"}, (
        f"data_provenance={geojson['data_provenance']!r} is not a valid schema enum value"
    )
    assert 0.0 <= geojson["oil_confidence"] <= 1.0, f"oil_confidence={geojson['oil_confidence']} out of [0,1]"
    assert isinstance(geojson["centroid"], list) and len(geojson["centroid"]) == 2, (
        "centroid must be a 2-element [lon, lat] list"
    )
    assert geojson["geometry"]["type"] in {"Polygon", "MultiPolygon"}, (
        f"geometry.type={geojson['geometry']['type']!r}, expected Polygon or MultiPolygon"
    )

    print(
        f"  PASS — spill_id={geojson['spill_id']}, area_km2={geojson['area_km2']:.4f}, "
        f"elongation_ratio={geojson['elongation_ratio']:.2f}, "
        f"thickness_class={geojson['thickness_class']}, "
        f"oil_confidence={geojson['oil_confidence']:.4f}, "
        f"execution_time_seconds={result['execution_time_seconds']:.2f}"
    )
    return geojson


def test_negative_sample(detector: OilSpillDetector) -> None:
    print(f"\n[TEST] Negative sample: {NEGATIVE_SAMPLE}")
    result = detector.predict(str(NEGATIVE_SAMPLE))

    assert result["has_oil"] is False, (
        f"Expected has_oil=False on a known-negative scene, got {result['has_oil']} "
        f"(oil_confidence={result['oil_confidence']:.4f})"
    )
    assert result["geojson"] is None, "Expected geojson=None when the Stage 1 gate closes."
    assert result["prob_map"] is None, (
        "prob_map is not None on a scene the classifier gated out — this means Stage 2 "
        "(the expensive segmenter) ran anyway. That defeats the entire point of the "
        "two-stage cascade (Detection_Model_Documentation.md §2) — treat this as a real "
        "bug in the gate logic, not a cosmetic issue."
    )
    print(f"  PASS — Stage 1 gate correctly halted execution (classifier P(oil)={result['oil_confidence']:.4f})")


def main() -> None:
    problems = _check_missing_inputs()
    if problems:
        print("Cannot run — required sample scenes are missing:")
        for p in problems:
            print(f"  - {p}")
        print(
            "\nThis is an environment/data problem, not a code problem — point "
            "POSITIVE_SAMPLE / NEGATIVE_SAMPLE at real files from your Part III split "
            "if your local layout differs from the default."
        )
        sys.exit(1)

    print("Loading OilSpillDetector (classifier + segmenter checkpoints)...")
    detector = OilSpillDetector()  # uses default checkpoint paths under checkpoints/

    geojson = test_positive_sample(detector)
    test_negative_sample(detector)

    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_GEOJSON, "w") as f:
        json.dump(geojson, f, indent=2)

    # Round-trip check: prove it's actually valid, re-loadable JSON, not
    # just a dict that happened to serialize without raising.
    with open(OUTPUT_GEOJSON) as f:
        reloaded = json.load(f)
    assert reloaded == geojson, "Round-tripped geojson does not match the in-memory geojson."
    print(f"\nSaved and verified: {OUTPUT_GEOJSON}")

    print("\nAll detection pipeline checks passed.")


if __name__ == "__main__":
    main()
