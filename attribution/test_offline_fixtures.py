"""
SIH26143 — Attribution subsystem
Offline tests against realistic FIXTURE data shaped exactly like GFW's own
documented example responses (see gfw_client.py docstring for the citations
each fixture is based on). These do NOT hit the network — this sandbox has
no egress, so this is the honest substitute for "I ran it against the live
API myself": every fixture below is copied/adapted from a real documented
example in GFW's or AISstream's own docs, not invented.

Run: python attribution/test_offline_fixtures.py
"""

from __future__ import annotations

import sys

from gfw_client import _normalize_4wings_entries, bbox_to_geojson_polygon, DATASET_AIS_PRESENCE
from aisstream_client import bbox_lonlat_to_aisstream_boxes, MUMBAI_GULF_BBOX_LONLAT
from feature_engineering import build_features, VesselFeatures, _distance_to_lane_km, _angle_diff_deg
from scorer import score_vessels, fuse_candidate_scores, SKLEARN_AVAILABLE
import project_paths

PASS = "PASS"
FAIL = "FAIL"
_results = []


def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    _results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and status == FAIL else ""))


def test_bbox_to_geojson():
    poly = bbox_to_geojson_polygon([60.0, 15.0, 73.0, 22.0])
    ring = poly["coordinates"][0]
    check("bbox_to_geojson_polygon: closed ring", ring[0] == ring[-1])
    check("bbox_to_geojson_polygon: 5 points", len(ring) == 5, str(ring))
    check("bbox_to_geojson_polygon: lon,lat order", ring[0] == [60.0, 15.0])


def test_aisstream_bbox_conversion():
    boxes = bbox_lonlat_to_aisstream_boxes(MUMBAI_GULF_BBOX_LONLAT)
    # Expect [[[minLat, minLon], [maxLat, maxLon]]]
    expected = [[[15.0, 60.0], [22.0, 73.0]]]
    check("aisstream bbox: lat-first conversion", boxes == expected, f"got {boxes}")


def test_4wings_normalize_shape_A_flat():
    """Flat shape, as seen in some simpler/legacy examples."""
    raw = [
        {"date": "2022-01-01", "mmsi": "412345678", "hours": 12.5, "lat": 18.9, "lon": 72.8},
        {"date": "2022-01-02", "mmsi": "412345678", "hours": 8.0, "lat": 19.0, "lon": 72.9},
    ]
    flat = _normalize_4wings_entries(raw, DATASET_AIS_PRESENCE)
    check("4wings shape A: flat passthrough count", len(flat) == 2, str(flat))
    check("4wings shape A: hours preserved", flat[0]["hours"] == 12.5)


def test_4wings_normalize_shape_B_nested():
    """
    Dataset-keyed shape, copied structurally from GFW's own documented
    example (globalfishingwatch.org/our-apis/documentation#introduction):
        entries: [ { "public-global-presence:v3.0": [ {...}, {...} ] } ]
    """
    raw = [
        {
            "public-global-presence:v3.0": [
                {"date": "2022-01-01", "flag": "USA", "hours": 156.25, "lat": -55.3, "lon": 35.2, "vesselIDs": 7},
                {"date": "2022-01-01", "flag": "ESP", "hours": 278.5, "lat": -55.1, "lon": 35.4, "vesselIDs": 13},
            ]
        }
    ]
    flat = _normalize_4wings_entries(raw, DATASET_AIS_PRESENCE)
    check("4wings shape B: nested unwrap count", len(flat) == 2, str(flat))
    check("4wings shape B: hours preserved", flat[0]["hours"] == 156.25)
    check("4wings shape B: source key tagged", flat[0].get("_source_dataset_key") == "public-global-presence:v3.0")


def test_4wings_normalize_shape_B_none_value():
    """
    Confirmed real bug hit on a live run (2026-08-31): the SAR presence
    dataset (public-global-sar-presence) can return `None` as the value for
    a dataset-keyed entry — a region/cell with zero unmatched detections —
    unlike AIS presence, which always seems to give a list. This crashed
    with `TypeError: 'NoneType' object is not iterable` before being fixed.
    """
    raw = [
        {"public-global-sar-presence:v3.0": [{"lat": 19.0, "lon": 70.0, "date": "2026-08-19", "matched": False}]},
        {"public-global-sar-presence:v3.0": None},
    ]
    flat = _normalize_4wings_entries(raw, "public-global-sar-presence:latest")
    check("4wings shape B: None value doesn't crash", True)
    check("4wings shape B: None entry skipped, real entry kept", len(flat) == 1, str(flat))


def test_project_paths_resolution():
    """
    Confirmed real bug: gfw_client._find_default_cache_dir() and
    aisstream_client._find_capture_dir() each independently guessed project
    root via an existence-based heuristic (checking whether data/cache or
    data/raw already existed, plus a sibling docs/ folder) — silently
    falling back to a CWD-relative path on a fresh clone where data/raw/
    doesn't exist yet (it's gitignored). Both now import from
    project_paths.py, which resolves unconditionally from __file__ location
    with no existence checks. This test confirms the resolved paths are
    exactly two levels under attribution/ and share a common ancestor.
    """
    check("project_paths: CACHE_DIR under PROJECT_ROOT/data/cache",
          project_paths.CACHE_DIR == project_paths.PROJECT_ROOT / "data" / "cache",
          str(project_paths.CACHE_DIR))
    check("project_paths: AISSTREAM_CAPTURE_DIR under PROJECT_ROOT/data/raw/aisstream_capture",
          project_paths.AISSTREAM_CAPTURE_DIR == project_paths.PROJECT_ROOT / "data" / "raw" / "aisstream_capture",
          str(project_paths.AISSTREAM_CAPTURE_DIR))
    # The actual bug: two different modules must resolve to the IDENTICAL
    # path, not just "a" path each.
    import gfw_client
    import feature_engineering
    check("project_paths: gfw_client's cache dir matches feature_engineering's capture-dir ancestor",
          gfw_client.DEFAULT_CACHE_DIR.parent == feature_engineering.AISSTREAM_CAPTURE_DIR.parent.parent,
          f"gfw={gfw_client.DEFAULT_CACHE_DIR}, fe={feature_engineering.AISSTREAM_CAPTURE_DIR}")


def test_fuse_candidate_scores_never_fabricates_without_drift():
    """
    Confirmed real bug: a prior version of fuse_candidate_scores defaulted
    proximity_score to 0.75 or 0.50, and vessel_type_prior to 0.65, on
    EVERY candidate whenever real Drift output wasn't supplied — which is
    always, right now, since Drift hasn't started (PROJECT_STATE.md). This
    produced a fully-populated `suspicion_score` that looked real but was
    substantially invented, tagged data_provenance="real_gfw" as if it
    weren't. This test locks in the fixed behavior: with no real Drift
    inputs supplied, suspicion_score/confidence_interval must stay None.
    """
    raw_candidates = [
        {
            "vessel_id": "111111111", "vessel_name": None,
            "suspicion_score": None, "confidence_interval": None,
            "evidence_trace": {
                "proximity_score": 0.0, "confession_match_score": 0.0,
                "anomaly_score": 0.8, "vessel_type_prior": None,
                "dominant_factor": "gap_duration_hours",
            },
            "data_provenance": "real_gfw",
            "_debug_imputed_features": [],
            "_pending": ["proximity_score (needs Drift subsystem)"],
        },
    ]
    # No drift_proximity_by_vessel, no forward_hypotheses supplied at all —
    # this is exactly today's real state of the project.
    fused = fuse_candidate_scores(raw_candidates)
    check("fuse: suspicion_score stays None with no real Drift input",
          fused[0]["suspicion_score"] is None, str(fused[0]))
    check("fuse: confidence_interval stays None with no real Drift input",
          fused[0]["confidence_interval"] is None, str(fused[0]))
    check("fuse: proximity_score NOT silently defaulted to 0.75/0.50",
          fused[0]["evidence_trace"]["proximity_score"] == 0.0, str(fused[0]["evidence_trace"]))
    check("fuse: pending note explains why fusion was skipped",
          any("fusion skipped" in p for p in fused[0].get("_pending", [])), str(fused[0].get("_pending")))


def test_fuse_candidate_scores_computes_when_real_drift_present():
    """
    The flip side: when real per-vessel proximity AND confession-match ARE
    supplied, fusion should actually run and produce a real, weighted score
    — the fix shouldn't have made this function permanently inert.
    """
    raw_candidates = [
        {
            "vessel_id": "222222222", "vessel_name": "Test Vessel",
            "suspicion_score": None, "confidence_interval": None,
            "evidence_trace": {
                "proximity_score": 0.0, "confession_match_score": 0.0,
                "anomaly_score": 0.9, "vessel_type_prior": 0.7,
                "dominant_factor": "gap_duration_hours",
            },
            "data_provenance": "real_gfw",
            "_debug_imputed_features": [],
        },
    ]
    fused = fuse_candidate_scores(
        raw_candidates,
        drift_proximity_by_vessel={"222222222": 0.85},
        forward_hypotheses=[{"vessel_id": "222222222", "shape_overlap_score": 0.6}],
    )
    check("fuse: suspicion_score computed when real drift inputs present",
          fused[0]["suspicion_score"] is not None, str(fused[0]))
    check("fuse: proximity_score reflects the real supplied value, not a default",
          fused[0]["evidence_trace"]["proximity_score"] == 0.85, str(fused[0]["evidence_trace"]))
    check("fuse: confidence_interval_method is explicitly labeled as a placeholder",
          fused[0].get("confidence_interval_method") == "placeholder_width_pending_bootstrap",
          str(fused[0]))


def test_feature_engineering_gap_events():
    """
    Event fixture copied structurally from GFW's documented Get-All-Events
    example response (docs/v3/events/get-all-events).
    """
    gap_events = [
        {
            "id": "a6e00481737d3e2c9903e1f565c51143",
            "type": "gap",
            "start": "2015-01-02T23:50:00.000Z",
            "end": "2015-01-04T02:20:00.000Z",  # 26.5 hours
            "vessel": {"flag": "ESP", "id": "a6e00481737d3e2c9903e1f565c51143",
                       "name": "Don tito", "ssvid": "775998121", "type": "FISHING"},
        }
    ]
    features = build_features(
        presence_entries=[{"mmsi": "775998121", "hours": 40.0}],
        gap_events=gap_events,
        loitering_events=[],
        encounter_events=[],
    )
    check("feature_engineering: vessel present after merge", "775998121" in features, str(features.keys()))
    vf = features["775998121"]
    check("feature_engineering: presence_hours merged", vf.presence_hours == 40.0)
    check("feature_engineering: gap_count", vf.gap_count == 1)
    check("feature_engineering: gap_duration_hours ~26.5", abs(vf.gap_duration_hours - 26.5) < 0.01, str(vf.gap_duration_hours))
    check("feature_engineering: speed_variance is None (no AISstream data)", vf.speed_variance is None)


def test_lane_distance_and_heading_diff():
    d_on_lane = _distance_to_lane_km(66.0, 20.5)  # exactly a waypoint
    d_off_lane = _distance_to_lane_km(66.0, 10.0)  # far south, off the lane
    check("lane distance: on-lane point is near-zero", d_on_lane < 1.0, str(d_on_lane))
    check("lane distance: off-lane point is far", d_off_lane > 500, str(d_off_lane))

    check("heading diff: simple case", _angle_diff_deg(10, 30) == 20)
    check("heading diff: wraparound case", abs(_angle_diff_deg(350, 10) - 20) < 1e-9,
          str(_angle_diff_deg(350, 10)))


def test_scorer_with_synthetic_but_labeled_population():
    """
    NOT fabricating "real" attribution data — this constructs a feature
    population directly (bypassing the real fetch layer) purely to verify
    the scorer's plumbing (imputation, sorting, evidence_trace shape)
    behaves correctly. Every one of these vessel_keys is a placeholder
    string, not a real MMSI, and this test never writes to data/cache/.
    """
    if not SKLEARN_AVAILABLE:
        check("scorer: sklearn available", False, "install scikit-learn + numpy")
        return

    pop = {
        "111111111": VesselFeatures(vessel_key="111111111", presence_hours=50, gap_count=0,
                                     gap_duration_hours=0, loitering_count=0, encounter_count=0),
        "222222222": VesselFeatures(vessel_key="222222222", presence_hours=5, gap_count=3,
                                     gap_duration_hours=40, loitering_count=2,
                                     loitering_duration_hours=10, encounter_count=1),
        "333333333": VesselFeatures(vessel_key="333333333", presence_hours=48, gap_count=0,
                                     gap_duration_hours=0, loitering_count=0, encounter_count=0),
    }
    results = score_vessels(pop)
    check("scorer: returns one record per vessel", len(results) == 3, str(len(results)))
    check("scorer: sorted descending by anomaly_score",
          all(results[i]["evidence_trace"]["anomaly_score"] >= results[i + 1]["evidence_trace"]["anomaly_score"]
              for i in range(len(results) - 1)))
    check("scorer: the vessel with real gaps+loitering scores highest",
          results[0]["vessel_id"] == "222222222", str(results[0]["vessel_id"]))
    check("scorer: evidence_trace has all schema fields",
          set(results[0]["evidence_trace"].keys()) == {
              "proximity_score", "confession_match_score", "anomaly_score",
              "vessel_type_prior", "dominant_factor",
          })
    check("scorer: pending fields are explicit, not silently omitted",
          "proximity_score (needs Drift subsystem)" in results[0]["_pending"][0]
          or any("Drift" in p for p in results[0]["_pending"]))


def main():
    test_bbox_to_geojson()
    test_aisstream_bbox_conversion()
    test_4wings_normalize_shape_A_flat()
    test_4wings_normalize_shape_B_nested()
    test_4wings_normalize_shape_B_none_value()
    test_project_paths_resolution()
    test_fuse_candidate_scores_never_fabricates_without_drift()
    test_fuse_candidate_scores_computes_when_real_drift_present()
    test_feature_engineering_gap_events()
    test_lane_distance_and_heading_diff()
    test_scorer_with_synthetic_but_labeled_population()

    n_fail = sum(1 for s, _, _ in _results if s == FAIL)
    print(f"\n{len(_results) - n_fail}/{len(_results)} checks passed.")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
