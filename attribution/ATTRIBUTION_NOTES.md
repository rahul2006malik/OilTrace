# Attribution subsystem — research notes & handoff (2026-08-31)

## What I did before writing any code

The prior chat's `gfw_client.py` explicitly flagged that it had never been run
against the live API. Rather than build further on unverified guesses, I
re-checked the real, current GFW API docs and AISstream docs directly
(`globalfishingwatch.org/our-apis/documentation`, `docs/v3/4wings`,
`docs/v3/events`, `docs/v3/vessels`, `docs/license-rate-limits`,
`aisstream.io/documentation`) on 2026-08-31, and rewrote the fetch layer
around what's actually documented, not what seemed plausible.

**I still could not make a live call myself** — this sandbox has no network
egress to `gateway.api.globalfishingwatch.org` or `stream.aisstream.io`. Every
shape below is grounded in a real, cited example from GFW/AISstream's own
docs; the offline tests (`test_offline_fixtures.py`) replay those exact
example shapes through the real parsing code and all 23 checks pass. But
that's still not the same as seeing our exact query hit the real endpoint —
**please run `fetch_demo_scenario.py` for real and paste back the console
output**, especially anything non-200.

## Concrete bugs/gaps fixed vs. the prior version

1. **4Wings report response nesting was unhandled.** GFW's own documented
   example shows `entries` as `[ {"public-global-presence:v3.0": [...]} ]` —
   a dataset-keyed wrapper, not a flat list. The prior code read
   `data["entries"]` and would have iterated dicts with no `hours`/`mmsi`
   fields, silently returning nothing useful. Fixed with
   `_normalize_4wings_entries()`, which handles both the flat and nested
   shapes and is tested against both in `test_offline_fixtures.py`.

2. **`group_by="FLAG"` cannot support per-vessel scoring.** A flag-level row
   has no vessel identity at all — you cannot build "this specific vessel is
   anomalous" features from "Panama-flagged vessels spent 156 hours here."
   Switched the default to `group_by="MMSI"` (confirmed valid alongside
   `VESSEL_ID`, `GEARTYPE`, `FLAGANDGEARTYPE` per GFW's own client docs).

3. **No vessel identity resolution existed.** `vessel_name` and
   `vessel_type_prior` were permanently `null` in the prior stub. Added
   `resolve_vessel_identity()` against the real Vessels API
   (`GET /v3/vessels/search?query=<ssvid>&datasets[0]=public-global-vessel-identity:latest`),
   wired into `fetch_demo_scenario.py` for the top-N scored candidates only
   (bounded, deliberate API usage, not one call per vessel in the region).

4. **Only gaps were fetched; encounters and loitering were skipped**, even
   though the project doc's own feature list (Section 7.3) asks for them.
   Added `fetch_encounter_events()` and `fetch_loitering_events()`.

5. **No SAR dark-vessel cross-check existed**, even though the project doc
   (Section 7.5) explicitly calls this out as a real, external reference
   point GFW itself provides. Added `fetch_sar_dark_vessel_candidates()`
   using the confirmed real query shape (`public-global-sar-presence:latest`,
   `filters[0]=matched='false'`), and a first-pass (deliberately
   conservative) `dark_vessel_alert` construction in `fetch_demo_scenario.py`.

6. **The scorer was a naive gap-duration-only heuristic**, not the
   `sklearn.ensemble.IsolationForest` the project doc actually specifies
   (Section 7.3). Rewrote as a real IsolationForest over the full feature
   set, with honest median-imputation for genuinely-missing features
   (flagged per-vessel, never silently zeroed) instead of hardcoding
   placeholders for everything except one heuristic number.

7. **`speed_variance` / `heading_change_rate` were never actually
   computable from the prior design** — GFW's presence dataset is gridded
   hours, not point tracks, so those two features structurally require the
   AISstream live capture. Added `feature_engineering.py` to merge both
   real sources, and made the dependency explicit rather than silently
   leaving those fields blank forever.

8. **AISstream capture had a real, easy-to-miss coordinate-order bug
   waiting to happen.** AISstream's `BoundingBoxes` are `[lat, lon]` pairs;
   every other bbox in this project (GFW client, schemas.md, the execution
   doc) is `[lon, lat]`. Wrote `bbox_lonlat_to_aisstream_boxes()` as the one
   conversion point, tested explicitly.

## Two things GFW's own docs are internally inconsistent about — flagged, not guessed

- **Encounters dataset name:** the Events API page's own "reminder" text says
  `public-global-encounters-events:latest` (plural), but a code sample on the
  same site uses `public-global-encounter-events:latest` (singular).
  `fetch_encounter_events()` tries plural first and automatically falls back
  to singular on a 404/422, logging which one actually worked — so we only
  have to resolve this ambiguity once, empirically, instead of guessing.
- **Presence data lag:** some GFW pages say "up to 96 hours ago", the current
  Python client README says "~5 days ago" for the same 4Wings presence
  product. `END_DATE` in `fetch_demo_scenario.py` is set comfortably inside
  both (a week back), so this shouldn't matter for the current window, but
  don't push `END_DATE` closer than ~5 days to "today" without checking
  `entries` length first.

## What's genuinely still pending (not a bug — a real dependency)

`proximity_score`, `confession_match_score`, `suspicion_score`, and
`confidence_interval` are placeholders in every candidate record. Per
`schemas.md` Section 7.4 / the project doc, these need Drift's
`origin_ensemble.json` and `forward_cone.geojson` — and Drift hasn't started
yet (per `PROJECT_STATE.md`). Each candidate's `_pending` list says exactly
this, so it's visible in the output rather than silently missing.

## How to actually run this

```bash
cd attribution/
pip install -r requirements.txt --break-system-packages   # if on the sandboxed setup; otherwise just pip install -r requirements.txt

# One-time sanity check (no network, no API key needed):
python test_offline_fixtures.py

# The real thing (needs GFW_API_TOKEN in your .env at the project root):
python fetch_demo_scenario.py

# Separately, to accumulate live AISstream data for the speed/heading
# features (needs AISSTREAM_API_KEY in .env), run this in the background
# during your normal work sessions, same pattern as before:
python aisstream_client.py
```

**Please paste back into this thread, verbatim, not paraphrased:**
1. The full console output of `fetch_demo_scenario.py`.
2. If step 1 (presence) returns 0 rows, the `_raw_entries_shape_sample`
   field from the cached `data/cache/ais_presence_*.json` file, so we can
   confirm which of the two documented shapes GFW is actually sending for
   our specific geojson-bbox query (as opposed to the named-region example
   in their docs).
3. Whichever encounters dataset name actually worked (singular or plural) —
   printed directly in the console output.
4. The resulting `data/cache/attribution_stub_result.json`.

Once I see real output, I'll tighten anything that needs it — the defensive
parsing above is a hedge against genuine documented ambiguity, not a
substitute for confirming against reality.
