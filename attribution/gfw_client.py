"""
SIH26143 — Attribution subsystem
GFW fetch-and-cache layer, v2.

WHY THIS REWRITE EXISTS
------------------------
A prior chat wrote a first version of this file but never ran it against the
live API (no network path from that sandbox). This version was produced after
re-checking every endpoint shape directly against GFW's live API docs
(globalfishingwatch.org/our-apis/documentation, docs/v3/4wings, docs/v3/events,
docs/v3/vessels) on 2026-08-31, and fixes several things the untested version
got wrong or left incomplete:

1. **4Wings report response nesting.** GFW's own documented example shows
   `entries` as a list of objects, each keyed by the dataset+version string
   (e.g. `"public-global-presence:v3.0"`) mapping to the actual list of
   records — NOT a flat list of records directly. The prior version assumed
   `data["entries"]` was already flat; it would have silently returned zero
   usable rows. This version normalizes both shapes defensively (see
   `_normalize_4wings_entries`) because the exact nesting can depend on
   whether you query by named region vs. raw geojson, and that distinction
   isn't fully pinned down in the public docs. **Please run this for real and
   paste back one raw un-normalized response** so we can lock this down
   instead of guessing twice.

2. **group-by=FLAG gives you flag-level aggregates, not per-vessel data.**
   The prior version defaulted to `group_by="FLAG"`, which cannot support
   per-vessel anomaly features (there's no vessel identity in a flag-level
   row). Attribution needs vessel-level granularity, so this version
   defaults to `group_by="MMSI"` for anything feeding the scorer. Confirmed
   valid group-by values (per GFW's own R client docs): FLAG, GEARTYPE,
   FLAGANDGEARTYPE, MMSI, VESSEL_ID.

3. **Added three things the prior version didn't attempt at all:**
   - Vessels API identity resolution (`resolve_vessel_identity`) — needed
     for `vessel_name` and `vessel_type_prior` in `attribution_result.json`,
     schemas.md Section 3. Without this every candidate would carry
     `vessel_name: null` forever.
   - SAR vessel detection pull with `matched=false` filter
     (`fetch_sar_dark_vessel_candidates`) — this is GFW's own production
     dark-vessel detector (radar-detected, non-AIS-matched objects), and the
     project doc (Section 7.5) explicitly calls out using it as a second,
     external reference point for the dark-vessel branch, not just an
     internal heuristic.
   - Encounters + loitering event fetchers, alongside gaps — the project
     doc's feature list (Section 7.3) explicitly wants encounter/loitering
     behavior, not just AIS gaps, and the previous version only fetched gaps.

4. **Confirmed real dataset IDs (2026-08-31), used throughout:**
   - AIS presence:        public-global-presence:latest
   - SAR vessel presence: public-global-sar-presence:latest
   - Gaps (AIS-disabling): public-global-gaps-events:latest
   - Encounters:          public-global-encounters-events:latest
     (GFW's UI copy uses this plural form; one code sample on the same site
     uses the singular "public-global-encounter-events:latest" — this is a
     genuine inconsistency in GFW's own docs, not a typo on our end. This
     client tries the plural form first and automatically retries with the
     singular form on a dataset-not-found-style 422, logging which one
     actually worked so we only have to discover this once.)
   - Loitering:           public-global-loitering-events:latest
   - Vessel identity:     public-global-vessel-identity:latest

5. **Rate limits, confirmed live:** GFW asks non-commercial users to stay
   under 50,000 requests/day and 1,500,000/month (globalfishingwatch.org/
   our-apis/documentation/docs/license-rate-limits). We are nowhere near
   that for a hackathon demo — the real constraint is the documented
   "one 4Wings report at a time per token" 429 behavior, already handled
   below with backoff.

6. **Confirmed live (2026-08-31), fixed in this version:** GFW's Events
   API POST endpoint returns HTTP 201 (Created) on a normal successful
   call, not 200. An earlier version of this file only treated 200 as
   success and raised a spurious "error" on a perfectly valid
   `{"total": 0, "entries": []}` response — i.e. it mistook "zero real
   events in this window" for "the request failed." Fixed by accepting
   the full 2xx range as success.

STILL UNVERIFIED (network-disabled sandbox — cannot make the live call myself)
-------------------------------------------------------------------------
Every parsing path below is grounded in a real documented example, but I
have not seen a live response for OUR specific query shape (geojson bbox,
not a named EEZ/region). Run `fetch_demo_scenario.py` and paste back:
  - one raw (unparsed) 4Wings presence response
  - one raw gaps-events response
  - the exact error body if anything comes back non-200
...and I'll tighten this file to match reality exactly rather than defend
against multiple possible shapes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("gfw_client")

GFW_API_BASE = "https://gateway.api.globalfishingwatch.org"
FOURWINGS_REPORT_URL = f"{GFW_API_BASE}/v3/4wings/report"
EVENTS_URL = f"{GFW_API_BASE}/v3/events"
VESSELS_SEARCH_URL = f"{GFW_API_BASE}/v3/vessels/search"
VESSELS_BY_ID_URL = f"{GFW_API_BASE}/v3/vessels/{{vessel_id}}"

# --- Confirmed dataset IDs (see module docstring, point 4) ------------------
DATASET_AIS_PRESENCE = "public-global-presence:latest"
DATASET_SAR_PRESENCE = "public-global-sar-presence:latest"
DATASET_GAPS_EVENTS = "public-global-gaps-events:latest"
DATASET_ENCOUNTERS_EVENTS_PRIMARY = "public-global-encounters-events:latest"
DATASET_ENCOUNTERS_EVENTS_FALLBACK = "public-global-encounter-events:latest"
DATASET_LOITERING_EVENTS = "public-global-loitering-events:latest"
DATASET_VESSEL_IDENTITY = "public-global-vessel-identity:latest"

try:
    from .project_paths import CACHE_DIR as DEFAULT_CACHE_DIR
except ImportError:
    from project_paths import CACHE_DIR as DEFAULT_CACHE_DIR


class GFWAPIError(RuntimeError):
    """Raised on a non-2xx response from the GFW API, with the parsed body attached."""

    def __init__(self, status_code: int, body: Any, request_desc: str):
        self.status_code = status_code
        self.body = body
        super().__init__(
            f"GFW API error {status_code} on {request_desc}: {json.dumps(body, default=str)[:800]}"
        )


def _get_token() -> str:
    token = os.environ.get("GFW_API_TOKEN")
    if not token:
        raise RuntimeError(
            "GFW_API_TOKEN not found in environment. Check your .env at the "
            "project root — PROJECT_STATE.md says it should already be there."
        )
    return token


def bbox_to_geojson_polygon(bbox: list[float]) -> dict:
    """
    bbox = [minLon, minLat, maxLon, maxLat] — the project's own convention
    (Mumbai-Gulf: [60.0, 15.0, 73.0, 22.0]). Returns a closed-ring GeoJSON
    Polygon in [lon, lat] order (GeoJSON spec order — NOT the same order
    AISstream.io uses for its BoundingBoxes; see aisstream_client.py for
    that conversion, it's a real, easy-to-miss bug source).
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    ring = [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def _cache_key(prefix: str, **parts: Any) -> str:
    raw = prefix + "|" + json.dumps(parts, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _write_cache(cache_dir: Path, key: str, payload: dict) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    max_retries: int = 3,
    request_desc: str = "",
) -> dict:
    """
    GFW's 4Wings report endpoint documents a hard rule: only one report per
    user/token at a time, else 429. We back off and retry on 429 everywhere,
    since it's cheap insurance even outside 4Wings.
    """
    last_error: Optional[GFWAPIError] = None
    for attempt in range(1, max_retries + 1):
        resp = requests.request(
            method, url, headers=headers, params=params, json=json_body, timeout=120
        )
        # Accept the full 2xx range, not just 200. Confirmed live (2026-08-31):
        # the Events API POST endpoint returns 201 (Created) on a normal
        # successful call, not 200 — a prior version of this file treated
        # 201 as an error and raised on a perfectly valid `{"total": 0,
        # "entries": []}` response. 0 real events in a window is an honest
        # result, not a failure.
        if 200 <= resp.status_code < 300:
            return resp.json()

        try:
            body = resp.json()
        except ValueError:
            body = {"raw_text": resp.text[:800]}

        err = GFWAPIError(resp.status_code, body, request_desc)

        if resp.status_code == 429:
            wait_s = 5 * attempt
            logger.warning(
                "429 rate-limited on %s, retrying in %ds (attempt %d/%d)",
                request_desc, wait_s, attempt, max_retries,
            )
            time.sleep(wait_s)
            last_error = err
            continue

        if resp.status_code == 524:
            raise GFWAPIError(
                524, body,
                request_desc + " (524 gateway timeout — the report may still be "
                               "processing server-side; GFW's docs point to the "
                               "last-report endpoint for recovery, not wired up here)"
            )

        # 401/403/404/422/503 etc. — don't retry, these won't fix themselves.
        raise err

    assert last_error is not None
    raise last_error


def _normalize_4wings_entries(raw_entries: list, dataset_id: str) -> list[dict]:
    """
    Handle both documented shapes of a 4Wings report response:

    Shape A (flat) — seen in some simple/legacy examples:
        entries: [ {date, flag, hours, lat, lon, vesselIDs}, ... ]

    Shape B (dataset-keyed, confirmed in GFW's own current docs) — each
    entries[i] is a dict with ONE key equal to "<dataset>:<version>" (e.g.
    "public-global-presence:v3.0"), mapping to a list of records:
        entries: [ { "public-global-presence:v3.0": [ {...}, {...} ] } ]

    This function always returns a flat list of record dicts, tagging each
    with which raw entries[] index it came from (useful for debugging which
    "region" a record belongs to, if the query implicitly created more than
    one). If shape B's key doesn't match the requested dataset_id's prefix,
    we still take it (GFW sometimes reports a different pinned version than
    what you requested with ":latest") but log a warning so it's visible.
    """
    flat: list[dict] = []
    dataset_prefix = dataset_id.split(":")[0]

    for region_idx, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            continue

        # Shape A: looks like a real record already (has typical fields).
        if any(k in item for k in ("hours", "date", "lat", "lon", "flag", "mmsi", "vesselId")):
            record = dict(item)
            record["_region_index"] = region_idx
            flat.append(record)
            continue

        # Shape B: single key that looks like "<dataset>:<version>".
        matched_key = None
        for key in item.keys():
            if key.split(":")[0] == dataset_prefix:
                matched_key = key
                break
        if matched_key is None and len(item) == 1:
            # Unknown dataset string but still a single-key wrapper — take it,
            # and say so, rather than silently dropping real data.
            matched_key = next(iter(item.keys()))
            logger.warning(
                "4Wings entries[%d] key %r didn't match expected dataset prefix %r — "
                "using it anyway. Paste this response back so we can confirm.",
                region_idx, matched_key, dataset_prefix,
            )
        if matched_key is not None:
            records = item.get(matched_key)
            if not records:
                continue
            if isinstance(records, list):
                for record in records:
                    if isinstance(record, dict):
                        rec = dict(record)
                        rec["_region_index"] = region_idx
                        rec["_source_dataset_key"] = matched_key
                        flat.append(rec)
            elif isinstance(records, dict):
                rec = dict(records)
                rec["_region_index"] = region_idx
                rec["_source_dataset_key"] = matched_key
                flat.append(rec)

    return flat


@dataclass
class AISPresenceResult:
    entries: list[dict]
    cache_path: Path
    from_cache: bool
    raw_response_sample: Any = None  # first ~2KB of the real raw response, for debugging


def fetch_ais_presence(
    bbox: list[float],
    start_date: str,
    end_date: str,
    *,
    temporal_resolution: str = "DAILY",
    spatial_resolution: str = "LOW",
    group_by: str = "MMSI",
    cache_dir: Path = DEFAULT_CACHE_DIR,
    force_refresh: bool = False,
) -> AISPresenceResult:
    """
    Real AIS vessel presence via the 4Wings report endpoint, dataset
    `public-global-presence:latest`.

    Confirmed live: data is available roughly 2012 -> ~5 days ago on the
    Map Visualization (4Wings) product per GFW's own Python client README
    (some GFW pages still say "96 hours" for the raw presence pipeline
    specifically — treat ~5 days as the safe upper bound and check
    `entries` length rather than trusting either number blindly).

    `group_by="MMSI"` (not the prior default "FLAG") because attribution
    needs per-vessel rows, not flag-level aggregates — see module docstring
    point 2. GFW's own docs confirm MMSI and VESSEL_ID are both valid
    group-by values.
    """
    key = _cache_key(
        "ais_presence", bbox=bbox, start=start_date, end=end_date,
        temporal_resolution=temporal_resolution, group_by=group_by,
        spatial_resolution=spatial_resolution,
    )
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists() and not force_refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return AISPresenceResult(entries=cached["entries"], cache_path=cache_path, from_cache=True)

    token = _get_token()
    geojson = bbox_to_geojson_polygon(bbox)

    params = {
        "format": "JSON",
        "group-by": group_by,
        "temporal-resolution": temporal_resolution,
        "datasets[0]": DATASET_AIS_PRESENCE,
        "date-range": f"{start_date},{end_date}",
        "spatial-resolution": spatial_resolution,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"geojson": geojson}

    data = _request_with_retry(
        "POST", FOURWINGS_REPORT_URL, headers=headers, params=params, json_body=body,
        request_desc=f"4wings/report AIS presence {bbox} {start_date}..{end_date}",
    )

    raw_entries = data.get("entries", [])
    entries = _normalize_4wings_entries(raw_entries, DATASET_AIS_PRESENCE)

    payload = {
        "data_provenance": "real_gfw",
        "dataset": DATASET_AIS_PRESENCE,
        "endpoint": "4wings/report",
        "query": {
            "bbox": bbox, "start_date": start_date, "end_date": end_date,
            "temporal_resolution": temporal_resolution, "group_by": group_by,
            "spatial_resolution": spatial_resolution,
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": len(entries),
        "entries": entries,
        "raw_metadata": {k: v for k, v in data.items() if k != "entries"},
        "_raw_entries_shape_sample": raw_entries[:1],  # so a human can eyeball the real shape
    }
    _write_cache(cache_dir, key, payload)
    return AISPresenceResult(
        entries=entries, cache_path=cache_path, from_cache=False,
        raw_response_sample=raw_entries[:1],
    )


@dataclass
class SARDetectionResult:
    entries: list[dict]
    cache_path: Path
    from_cache: bool


def fetch_sar_dark_vessel_candidates(
    bbox: list[float],
    start_date: str,
    end_date: str,
    *,
    spatial_resolution: str = "HIGH",
    temporal_resolution: str = "HOURLY",
    cache_dir: Path = DEFAULT_CACHE_DIR,
    force_refresh: bool = False,
) -> SARDetectionResult:
    """
    Real radar (SAR) vessel detections that did NOT match any AIS broadcast
    — GFW's own production dark-vessel detector. This is the "second
    reference point" the project doc (Section 7.5) explicitly wants: if our
    own attribution pipeline flags a dark vessel in the same area/window,
    GFW's SAR layer flagging something too is real, external corroboration.

    Confirmed real query shape from GFW's own docs: dataset
    `public-global-sar-presence:latest`, filtered with `matched='false'`.
    Uses `filters[0]` per GFW's documented example rather than a body
    field — this is a 4Wings-report-specific filter syntax, distinct from
    the Events API's filter params.
    """
    key = _cache_key(
        "sar_dark_vessels", bbox=bbox, start=start_date, end=end_date,
        spatial_resolution=spatial_resolution, temporal_resolution=temporal_resolution,
    )
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists() and not force_refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return SARDetectionResult(entries=cached["entries"], cache_path=cache_path, from_cache=True)

    token = _get_token()
    geojson = bbox_to_geojson_polygon(bbox)

    params = {
        "format": "JSON",
        "spatial-resolution": spatial_resolution,
        "temporal-resolution": temporal_resolution,
        "datasets[0]": DATASET_SAR_PRESENCE,
        "date-range": f"{start_date},{end_date}",
        "filters[0]": "matched='false'",
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"geojson": geojson}

    data = _request_with_retry(
        "POST", FOURWINGS_REPORT_URL, headers=headers, params=params, json_body=body,
        request_desc=f"4wings/report SAR dark-vessel {bbox} {start_date}..{end_date}",
    )
    raw_entries = data.get("entries", [])
    entries = _normalize_4wings_entries(raw_entries, DATASET_SAR_PRESENCE)

    payload = {
        "data_provenance": "real_gfw",
        "dataset": DATASET_SAR_PRESENCE,
        "endpoint": "4wings/report (SAR, matched=false)",
        "query": {"bbox": bbox, "start_date": start_date, "end_date": end_date},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": len(entries),
        "entries": entries,
    }
    _write_cache(cache_dir, key, payload)
    return SARDetectionResult(entries=entries, cache_path=cache_path, from_cache=False)


@dataclass
class EventsResult:
    events: list[dict]
    cache_path: Path
    from_cache: bool
    dataset_used: str
    total_available: int = 0  # real total per GFW's `total` field — may exceed
                                # len(events) if `limit` truncated the response


def _fetch_events(
    dataset_candidates: list[str],
    bbox: list[float],
    start_date: str,
    end_date: str,
    *,
    cache_prefix: str,
    limit: int,
    cache_dir: Path,
    force_refresh: bool,
    extra_body: Optional[dict] = None,
    max_pages: int = 10,
) -> EventsResult:
    """
    Shared Events-API fetcher. Tries each dataset id in `dataset_candidates`
    in order, falling back to the next on a 404/422 (handles the
    encounters-dataset-name inconsistency noted in the module docstring).

    Confirmed live (2026-08-31): a real pull returned exactly `limit` events
    (500/500 loitering events) — meaning the window/region has MORE real
    events than one page holds. Without pagination, everything past the
    first page is silently lost. This follows GFW's own `nextOffset` field
    (confirmed real from the actual response:
    `{"limit": 500, "offset": 0, "nextOffset": None, "total": 0, ...}`)
    until all real events are fetched, `total` is reached, or `max_pages`
    is hit as a hard safety cap.
    """
    key = _cache_key(cache_prefix, bbox=bbox, start=start_date, end=end_date, limit=limit)
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists() and not force_refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return EventsResult(
            events=cached["events"], cache_path=cache_path, from_cache=True,
            dataset_used=cached.get("dataset", dataset_candidates[0]),
            total_available=cached.get("total_events_in_window", len(cached["events"])),
        )

    token = _get_token()
    geojson = bbox_to_geojson_polygon(bbox)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    last_err: Optional[GFWAPIError] = None
    dataset_used = None
    all_events: list[dict] = []
    total_reported = None
    offset = 0
    page = 0

    while True:
        page += 1
        params = {"offset": offset, "limit": limit}
        data = None
        for dataset_id in dataset_candidates:
            body = {
                "datasets": [dataset_id],
                "startDate": start_date,
                "endDate": end_date,
                "geometry": geojson,
            }
            if extra_body:
                body.update(extra_body)
            try:
                data = _request_with_retry(
                    "POST", EVENTS_URL, headers=headers, params=params, json_body=body,
                    request_desc=f"events {dataset_id} {bbox} {start_date}..{end_date} offset={offset}",
                )
                dataset_used = dataset_id
                break
            except GFWAPIError as e:
                last_err = e
                if e.status_code in (404, 422) and len(dataset_candidates) > 1:
                    logger.warning(
                        "Dataset %r rejected (%d) — trying next candidate.",
                        dataset_id, e.status_code,
                    )
                    continue
                raise

        if data is None:
            assert last_err is not None
            raise last_err

        page_events = data.get("entries", [])
        all_events.extend(page_events)
        total_reported = data.get("total", len(all_events))
        next_offset = data.get("nextOffset")

        logger.info(
            "%s page %d: +%d events (running total %d / reported total %s)",
            dataset_used, page, len(page_events), len(all_events), total_reported,
        )

        if next_offset is None or not page_events or page >= max_pages:
            if page >= max_pages and next_offset is not None:
                logger.warning(
                    "Hit max_pages=%d for %s with more real data still available "
                    "(nextOffset=%s) — raise max_pages if you need the full set.",
                    max_pages, dataset_used, next_offset,
                )
            break
        offset = next_offset

    payload = {
        "data_provenance": "real_gfw",
        "dataset": dataset_used,
        "endpoint": "events",
        "query": {"bbox": bbox, "start_date": start_date, "end_date": end_date, "limit": limit},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_events_in_window": total_reported,
        "returned_events": len(all_events),
        "pages_fetched": page,
        "events": all_events,
    }
    _write_cache(cache_dir, key, payload)
    return EventsResult(
        events=all_events, cache_path=cache_path, from_cache=False, dataset_used=dataset_used,
        total_available=total_reported if total_reported is not None else len(all_events),
    )


def fetch_gap_events(
    bbox: list[float], start_date: str, end_date: str, *,
    limit: int = 500, cache_dir: Path = DEFAULT_CACHE_DIR, force_refresh: bool = False,
) -> EventsResult:
    """Real AIS-disabling ("gap") events — the core dark-vessel-behavior signal."""
    return _fetch_events(
        [DATASET_GAPS_EVENTS], bbox, start_date, end_date,
        cache_prefix="gap_events", limit=limit, cache_dir=cache_dir, force_refresh=force_refresh,
    )


def fetch_encounter_events(
    bbox: list[float], start_date: str, end_date: str, *,
    limit: int = 500, cache_dir: Path = DEFAULT_CACHE_DIR, force_refresh: bool = False,
) -> EventsResult:
    """
    Real vessel-to-vessel encounter events (fishing-carrier, tanker-fishing,
    etc.) — feeds the anomaly feature set per project doc Section 7.3.
    Tries the plural dataset name first, falls back to singular.
    """
    return _fetch_events(
        [DATASET_ENCOUNTERS_EVENTS_PRIMARY, DATASET_ENCOUNTERS_EVENTS_FALLBACK],
        bbox, start_date, end_date,
        cache_prefix="encounter_events", limit=limit, cache_dir=cache_dir, force_refresh=force_refresh,
    )


def fetch_loitering_events(
    bbox: list[float], start_date: str, end_date: str, *,
    limit: int = 500, cache_dir: Path = DEFAULT_CACHE_DIR, force_refresh: bool = False,
) -> EventsResult:
    """Real loitering events — feeds 'loitering time near spill window' feature."""
    return _fetch_events(
        [DATASET_LOITERING_EVENTS], bbox, start_date, end_date,
        cache_prefix="loitering_events", limit=limit, cache_dir=cache_dir, force_refresh=force_refresh,
    )


# ----------------------------------------------------------------------------
# Vessels API — identity resolution (new in this rewrite; see docstring pt 3)
# ----------------------------------------------------------------------------

@dataclass
class VesselIdentity:
    query: str
    resolved: bool
    vessel_id: Optional[str]
    shipname: Optional[str]
    flag: Optional[str]
    shiptype: Optional[str]
    ssvid: Optional[str]
    raw: Optional[dict]


def resolve_vessel_identity(
    ssvid_or_mmsi: str,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    force_refresh: bool = False,
) -> VesselIdentity:
    """
    Resolve an MMSI/ssvid to a real vessel identity (name, flag, type) via
    the Vessels API search endpoint. Confirmed real shape: GET
    /v3/vessels/search?query=<ssvid>&datasets[0]=public-global-vessel-identity:latest
    returns `entries[].selfReportedInfo[]` with `shipname`, `flag`,
    `shiptype`, `ssvid`, `id`.

    This is what fills `vessel_name` and gives a real `vessel_type_prior`
    basis in attribution_result.json (schemas.md Section 3) instead of the
    `null` placeholders the prior version shipped with.
    """
    key = _cache_key("vessel_identity", query=ssvid_or_mmsi)
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists() and not force_refresh:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return VesselIdentity(**cached)

    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "query": str(ssvid_or_mmsi),
        "datasets[0]": DATASET_VESSEL_IDENTITY,
        "limit": 5,
    }
    try:
        data = _request_with_retry(
            "GET", VESSELS_SEARCH_URL, headers=headers, params=params,
            request_desc=f"vessels/search {ssvid_or_mmsi}",
        )
    except GFWAPIError as e:
        logger.warning("Vessel identity lookup failed for %s: %s", ssvid_or_mmsi, e)
        result = VesselIdentity(
            query=ssvid_or_mmsi, resolved=False, vessel_id=None,
            shipname=None, flag=None, shiptype=None, ssvid=None, raw=None,
        )
        _write_cache(cache_dir, key, result.__dict__)
        return result

    entries = data.get("entries", [])
    if not entries:
        result = VesselIdentity(
            query=ssvid_or_mmsi, resolved=False, vessel_id=None,
            shipname=None, flag=None, shiptype=None, ssvid=None, raw=None,
        )
    else:
        best = entries[0]
        self_reported = best.get("selfReportedInfo") or []
        info = self_reported[0] if self_reported else {}
        result = VesselIdentity(
            query=ssvid_or_mmsi, resolved=True,
            vessel_id=info.get("id"),
            shipname=info.get("shipname"),
            flag=info.get("flag"),
            shiptype=info.get("shiptype"),
            ssvid=info.get("ssvid"),
            raw=best,
        )
    _write_cache(cache_dir, key, result.__dict__)
    return result
