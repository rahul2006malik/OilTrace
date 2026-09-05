"""
SIH26143 — Attribution subsystem
End-to-end (for this subsystem) demo-scenario builder, v2.

WHAT CHANGED FROM THE PRIOR CHAT'S VERSION
---------------------------------------------
The prior `fetch_demo_scenario.py` only did steps 1-2 (presence + gaps) and
left everything else as a separate, disconnected `scorer_stub.py` with a
naive heuristic. This version:

  1. Pulls presence at vessel-level granularity (group_by=MMSI, not FLAG —
     see gfw_client.py docstring point 2), plus gaps, loitering, encounters,
     AND the SAR dark-vessel cross-check — five real GFW pulls instead of
     two, matching Project Doc Section 7.1's full data-source list.
  2. Folds in any accumulated real AISstream live capture for the same
     region, if present, for the two features that GFW's gridded presence
     data structurally cannot provide (speed variance, heading-change rate).
  3. Resolves real vessel identity (name/flag/type) for the top-N vessels
     by anomaly score, via the Vessels API — so `vessel_name` and
     `vessel_type_prior` in the output aren't permanently null.
  4. Runs the real IsolationForest scorer (scorer.py), not a hand-rolled
     gap-duration heuristic.
  5. Constructs a first-pass `dark_vessel_alert` using the real SAR
     cross-check: if GFW's own radar-vs-AIS mismatch layer shows unmatched
     detections in the window with no strong AIS candidate nearby, that's
     flagged — matching Project Doc Section 7.5's requirement that this be
     a first-class output, not an afterthought.
  6. Writes one combined, schema-shaped draft of `attribution_result.json`
     to data/cache/, in addition to the individual raw-pull caches (kept
     for debugging/re-use, same as before).

STILL A DRAFT, NOT THE REAL attribution_result.json
------------------------------------------------------
`proximity_score`, `confession_match_score`, `suspicion_score`, and
`confidence_interval` are still placeholders — see scorer.py's docstring.
This is honest and expected at this stage (Drift subsystem hasn't started
per PROJECT_STATE.md), not a bug in this file.

I have NOT run this against the live GFW/AISstream services myself — no
network path from this sandbox. Every endpoint shape used here was
re-verified against GFW's current live documentation before writing this
(see gfw_client.py's docstring for citations), but this is still the
first real end-to-end run. Please run it and paste back:
  - console output in full
  - if anything 4xx/5xx's, the full error body (not paraphrased)
  - the resulting attribution_stub_result.json so we can sanity-check the
    real feature distributions together
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BBOX = [60.0, 15.0, 73.0, 22.0]  # Mumbai-Gulf corridor, [minLon, minLat, maxLon, maxLat]

# GFW AIS presence lags ~5 days behind "now" per GFW's own client docs (some
# pages say 96h specifically for presence) — keep end_date comfortably
# inside that. Keep the window short (a few days to ~2 weeks) per GFW's own
# guidance to avoid report timeouts.
START_DATE = "2026-08-18"
END_DATE = "2026-08-25"

try:
    from project_paths import CACHE_DIR
except ImportError:
    CACHE_DIR = Path("data/cache")  # last-resort fallback; project_paths.py should always be importable

TOP_N_FOR_IDENTITY_RESOLUTION = 8  # keep Vessels API calls small and deliberate


def main() -> int:
    try:
        import gfw_client as gfw
        import feature_engineering as fe
        import scorer as sc
    except ImportError as e:
        print(f"[fetch_demo_scenario] Import failed: {e}")
        print("Run from the attribution/ directory (or put it on PYTHONPATH), "
              "and pip install -r requirements.txt first.")
        return 1

    print(f"[fetch_demo_scenario] Mumbai-Gulf bbox={BBOX}, window={START_DATE}..{END_DATE}")

    # ------------------------------------------------------------------
    # Step 1: real AIS vessel presence, vessel-level (group_by=MMSI)
    # ------------------------------------------------------------------
    print("\n[1/5] AIS vessel presence (4Wings, group_by=MMSI)...")
    try:
        presence = gfw.fetch_ais_presence(bbox=BBOX, start_date=START_DATE, end_date=END_DATE)
    except gfw.GFWAPIError as e:
        return _fail("presence", e)
    except RuntimeError as e:
        print(f"  {e}")
        return 1
    print(f"  {'(cache) ' if presence.from_cache else ''}{len(presence.entries)} presence rows.")
    if presence.entries:
        print("  sample:", json.dumps(presence.entries[0], default=str)[:400])
    else:
        print("  Zero rows — could be genuinely sparse coverage for this exact "
              "window/bbox/group-by, OR the 4Wings response nesting didn't match "
              "what this client expects (see gfw_client.py docstring point 1). "
              "Check the cached raw file's `_raw_entries_shape_sample` field.")

    # ------------------------------------------------------------------
    # Step 2: real AIS-disabling (gap) events
    # ------------------------------------------------------------------
    print("\n[2/5] AIS-disabling (gap) events...")
    try:
        gaps = gfw.fetch_gap_events(bbox=BBOX, start_date=START_DATE, end_date=END_DATE)
    except gfw.GFWAPIError as e:
        return _fail("gap events", e)
    print(f"  {'(cache) ' if gaps.from_cache else ''}{len(gaps.events)} gap events "
          f"(dataset used: {gaps.dataset_used}).")

    # ------------------------------------------------------------------
    # Step 3: real loitering + encounter events
    # ------------------------------------------------------------------
    print("\n[3/5] Loitering + encounter events...")
    try:
        loitering = gfw.fetch_loitering_events(bbox=BBOX, start_date=START_DATE, end_date=END_DATE)
    except gfw.GFWAPIError as e:
        return _fail("loitering events", e)
    try:
        encounters = gfw.fetch_encounter_events(bbox=BBOX, start_date=START_DATE, end_date=END_DATE)
    except gfw.GFWAPIError as e:
        return _fail("encounter events", e)
    print(f"  {len(loitering.events)} loitering events "
          f"(dataset used: {loitering.dataset_used}, total in window: {loitering.total_available}).")
    if loitering.total_available and len(loitering.events) < loitering.total_available:
        print(f"  NOTE: only fetched {len(loitering.events)} of {loitering.total_available} real "
              f"loitering events (hit max_pages safety cap) — raise max_pages in gfw_client.py "
              f"if you need the complete set for scoring.")
    print(f"  {len(encounters.events)} encounter events "
          f"(dataset used: {encounters.dataset_used}, total in window: {encounters.total_available}).")

    # ------------------------------------------------------------------
    # Step 4: real SAR dark-vessel cross-check (matched=false)
    # ------------------------------------------------------------------
    print("\n[4/5] SAR dark-vessel cross-check (matched=false)...")
    try:
        sar = gfw.fetch_sar_dark_vessel_candidates(bbox=BBOX, start_date=START_DATE, end_date=END_DATE)
        print(f"  {'(cache) ' if sar.from_cache else ''}{len(sar.entries)} unmatched SAR detections.")
    except gfw.GFWAPIError as e:
        # Not fatal — SAR presence dataset access can be more restricted than
        # the base presence dataset. Report it plainly and continue.
        print(f"  SAR pull failed ({e.status_code}): {e.body}")
        print("  Continuing without the SAR cross-check — dark_vessel_alert will "
              "be based on AIS-only evidence for this run.")
        sar = None

    # ------------------------------------------------------------------
    # Feature engineering: merge GFW + any real AISstream capture on disk
    # ------------------------------------------------------------------
    print("\n[Feature engineering] Merging GFW events/presence with AISstream capture...")
    aisstream_files = fe.discover_aisstream_files()
    print(f"  Found {len(aisstream_files)} AISstream capture file(s) on disk.")
    features = fe.build_features(
        presence_entries=presence.entries,
        gap_events=gaps.events,
        loitering_events=loitering.events,
        encounter_events=encounters.events,
        aisstream_jsonl_paths=aisstream_files,
    )
    print(f"  {len(features)} distinct vessels (by MMSI/ssvid) across all real sources.")

    # ------------------------------------------------------------------
    # Step 5: real IsolationForest scoring
    # ------------------------------------------------------------------
    print("\n[5/5] Scoring (IsolationForest over the real feature set)...")
    try:
        candidates = sc.score_vessels(features)
    except RuntimeError as e:
        print(f"  {e}")
        return 1
    print(f"  Scored {len(candidates)} candidates.")

    # ------------------------------------------------------------------
    # Resolve real identity for the top-N candidates only (deliberate,
    # bounded number of Vessels API calls — not one per vessel).
    # ------------------------------------------------------------------
    print(f"\n[Identity] Resolving real vessel identity for top {TOP_N_FOR_IDENTITY_RESOLUTION}...")
    for cand in candidates[:TOP_N_FOR_IDENTITY_RESOLUTION]:
        identity = gfw.resolve_vessel_identity(cand["vessel_id"])
        if identity.resolved:
            cand["vessel_name"] = identity.shipname
            cand["evidence_trace"]["vessel_type_prior"] = identity.shiptype
            cand["_debug_identity"] = {
                "flag": identity.flag, "shiptype": identity.shiptype,
                "resolved_vessel_id": identity.vessel_id,
            }
            print(f"  {cand['vessel_id']} -> {identity.shipname or '(no name)'} "
                  f"({identity.shiptype or 'unknown type'}, flag={identity.flag})")
        else:
            print(f"  {cand['vessel_id']} -> not resolved (no matching registry entry)")

    # ------------------------------------------------------------------
    # First-pass dark-vessel alert: real SAR unmatched detections present,
    # AND the strongest AIS candidate doesn't clearly explain the area.
    # This is intentionally conservative/simple until Drift's origin cone
    # exists to do real spatial overlap — see _pending note in the output.
    # ------------------------------------------------------------------
    dark_vessel_alert = False
    dark_vessel_note = "No SAR cross-check available this run."
    if sar is not None:
        if sar.entries and (not candidates or candidates[0]["evidence_trace"]["anomaly_score"] < 0.6):
            dark_vessel_alert = True
            dark_vessel_note = (
                f"{len(sar.entries)} unmatched SAR detection(s) in window/region, "
                "and no AIS candidate scored strongly enough to confidently explain "
                "them. PRELIMINARY — proper dark-vessel logic needs spatial overlap "
                "with Drift's origin cone (Section 7.5), not just 'anomaly score low'."
            )
        elif sar.entries:
            dark_vessel_note = (
                f"{len(sar.entries)} unmatched SAR detection(s) present, but a "
                "high-anomaly AIS candidate also exists in the same pull — not "
                "flagging dark-vessel without real spatial correlation (pending Drift)."
            )
        else:
            dark_vessel_note = "No unmatched SAR detections in this window/region."

    result = {
        "spill_id": None,  # this run isn't tied to a specific detection yet — see note below
        "candidates": candidates,
        "dark_vessel_alert": dark_vessel_alert,
        "dark_vessel_note": dark_vessel_note,
        "top_k_recovery": {"k": 3, "recovered": None, "confidence": None},
        "_meta": {
            "note": (
                "spill_id is None because this is a standalone Attribution-subsystem "
                "smoke test against real ambient traffic, not a run tied to a real "
                "Detection output yet. Per schemas.md, spill_id is the join key across "
                "all three artifacts and must be populated once this is wired into "
                "/pipeline/run alongside a real slick_detection.geojson."
            ),
            "bbox": BBOX, "start_date": START_DATE, "end_date": END_DATE,
            "aisstream_files_used": [str(p) for p in aisstream_files],
        },
    }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CACHE_DIR / "attribution_stub_result.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\n[fetch_demo_scenario] Wrote {out_path}")
    print("[fetch_demo_scenario] Done.")
    return 0


def _fail(step_name: str, e) -> int:
    print(f"  GFW API error {e.status_code} on {step_name}: {e.body}")
    print("  Paste this full error back into the thread — don't paraphrase it.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
