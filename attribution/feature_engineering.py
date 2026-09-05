"""
SIH26143 — Attribution subsystem
Feature engineering: turns real GFW presence/events + real AISstream live
captures into one feature row per vessel, ready for IsolationForest.

DESIGN NOTE — why two data sources are combined instead of one
-----------------------------------------------------------------
GFW's 4Wings AIS Vessel Presence dataset is *gridded and hourly/daily
aggregated* — it tells you total hours a vessel(-group) spent in a cell,
not individual position pings. That means it CANNOT support "speed
variance" or "heading-change rate" as literal per-ping features, no matter
how it's queried. Those two features can only come from actual point-level
track data — which, in this project's real-data-first design, is exactly
what the AISstream.io live capture provides (Project Doc Section 7.1,
point 2). This is a real architectural constraint, not a shortcut:

    Feature                          | Real source
    ----------------------------------|---------------------------------
    speed_variance                    | AISstream live capture only
    heading_change_rate               | AISstream live capture only
    presence_hours_in_region          | GFW 4Wings presence (per-vessel)
    gap_duration_hours / gap_count    | GFW Events (gaps)
    loitering_duration_hours / count  | GFW Events (loitering)
    encounter_count                   | GFW Events (encounters)
    lane_deviation_km                 | Either source, if position present

A vessel with zero AISstream samples during the capture window will
legitimately have `speed_variance = None` / `heading_change_rate = None` —
that's an honest missing-data gap (matches schemas.md's "no silent
synthetic substitution" rule), NOT a bug to paper over with a fabricated 0.
The scorer (scorer.py) imputes missing features explicitly and flags which
ones were imputed per vessel, rather than pretending they were observed.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from .project_paths import AISSTREAM_CAPTURE_DIR
except ImportError:
    from project_paths import AISSTREAM_CAPTURE_DIR

# Rough Mumbai-Gulf shipping lane centerline, used only as an approximate
# reference for "distance from expected lane centerline" (Project Doc
# Section 7.3). This is NOT claimed to be an authoritative traffic
# separation scheme — it's a coarse great-circle-ish polyline connecting
# Mumbai's approaches to the Strait of Hormuz approaches, good enough to
# rank vessels by relative deviation, not to make legal claims.
MUMBAI_GULF_LANE_WAYPOINTS = [
    (72.8, 18.95),   # Mumbai approaches
    (70.0, 19.5),
    (66.0, 20.5),
    (61.5, 21.5),
    (56.5, 22.5),    # Strait of Hormuz approaches
]


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _distance_to_lane_km(lon: float, lat: float, waypoints=MUMBAI_GULF_LANE_WAYPOINTS) -> float:
    """Minimum distance from (lon,lat) to any segment of the lane polyline,
    approximated by checking distance to each waypoint and each segment
    midpoint — deliberately simple (no great-circle cross-track formula)
    since this is a coarse ranking feature, not a navigation product."""
    best = float("inf")
    pts = list(waypoints)
    for i in range(len(pts) - 1):
        lon1, lat1 = pts[i]
        lon2, lat2 = pts[i + 1]
        mid_lon, mid_lat = (lon1 + lon2) / 2, (lat1 + lat2) / 2
        for plon, plat in ((lon1, lat1), (mid_lon, mid_lat), (lon2, lat2)):
            d = _haversine_km(lon, lat, plon, plat)
            best = min(best, d)
    return best


def _angle_diff_deg(a: float, b: float) -> float:
    """Smallest signed difference between two compass headings, in degrees."""
    d = (b - a + 180) % 360 - 180
    return abs(d)


@dataclass
class VesselFeatures:
    vessel_key: str  # ssvid/mmsi as string — the join key across all sources
    presence_hours: Optional[float] = None
    gap_count: int = 0
    gap_duration_hours: float = 0.0
    loitering_count: int = 0
    loitering_duration_hours: float = 0.0
    encounter_count: int = 0
    speed_variance: Optional[float] = None
    heading_change_rate: Optional[float] = None  # mean abs deg change per position update
    mean_lane_deviation_km: Optional[float] = None
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    last_timestamp: Optional[str] = None
    aisstream_position_count: int = 0
    sources: list[str] = field(default_factory=list)  # which real sources contributed

    def to_dict(self) -> dict[str, Any]:
        return {
            "vessel_key": self.vessel_key,
            "presence_hours": self.presence_hours,
            "gap_count": self.gap_count,
            "gap_duration_hours": round(self.gap_duration_hours, 3),
            "loitering_count": self.loitering_count,
            "loitering_duration_hours": round(self.loitering_duration_hours, 3),
            "encounter_count": self.encounter_count,
            "speed_variance": self.speed_variance,
            "heading_change_rate": self.heading_change_rate,
            "mean_lane_deviation_km": self.mean_lane_deviation_km,
            "last_lat": self.last_lat,
            "last_lon": self.last_lon,
            "last_timestamp": self.last_timestamp,
            "aisstream_position_count": self.aisstream_position_count,
            "sources": sorted(set(self.sources)),
        }


def _vessel_key_from_gfw_record(record: dict) -> Optional[str]:
    for field_name in ("mmsi", "ssvid", "vesselId", "vessel_id"):
        v = record.get(field_name)
        if v:
            return str(v)
    return None


def _vessel_key_from_event(event: dict) -> Optional[str]:
    vessel = event.get("vessel", {}) or {}
    v = vessel.get("ssvid") or vessel.get("id")
    return str(v) if v else None


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_features(
    presence_entries: list[dict],
    gap_events: list[dict],
    loitering_events: list[dict],
    encounter_events: list[dict],
    aisstream_jsonl_paths: Optional[list[Path]] = None,
) -> dict[str, VesselFeatures]:
    """
    Merge every real source keyed by vessel (ssvid/MMSI as string). Returns
    a dict of vessel_key -> VesselFeatures. Callers should treat any `None`
    field as genuinely missing, not zero.
    """
    features: dict[str, VesselFeatures] = {}

    def get_or_create(key: str) -> VesselFeatures:
        if key not in features:
            features[key] = VesselFeatures(vessel_key=key)
        return features[key]

    # --- GFW 4Wings presence (per-vessel, if group_by=MMSI/VESSEL_ID) -------
    presence_hours_by_vessel: dict[str, float] = defaultdict(float)
    for rec in presence_entries:
        key = _vessel_key_from_gfw_record(rec)
        if not key:
            continue
        hours = rec.get("hours")
        if hours is not None:
            presence_hours_by_vessel[key] += float(hours)
        f = get_or_create(key)
        if rec.get("lat") is not None and rec.get("lon") is not None:
            f.last_lat = float(rec["lat"])
            f.last_lon = float(rec["lon"])
        if rec.get("date") or rec.get("entryTimestamp"):
            f.last_timestamp = str(rec.get("date") or rec.get("entryTimestamp"))

    for key, hours in presence_hours_by_vessel.items():
        f = get_or_create(key)
        f.presence_hours = hours
        f.sources.append("real_gfw_presence")

    # --- GFW gap events ------------------------------------------------------
    for ev in gap_events:
        key = _vessel_key_from_event(ev)
        if not key:
            continue
        f = get_or_create(key)
        f.gap_count += 1
        f.sources.append("real_gfw_gaps")
        if ev.get("lat") is not None and ev.get("lon") is not None:
            f.last_lat = float(ev["lat"])
            f.last_lon = float(ev["lon"])
        if ev.get("start"):
            f.last_timestamp = str(ev["start"])
        start, end = _parse_iso(ev.get("start")), _parse_iso(ev.get("end"))
        if start and end:
            f.gap_duration_hours += (end - start).total_seconds() / 3600.0

    # --- GFW loitering events -------------------------------------------------
    for ev in loitering_events:
        key = _vessel_key_from_event(ev)
        if not key:
            continue
        f = get_or_create(key)
        f.loitering_count += 1
        f.sources.append("real_gfw_loitering")
        if ev.get("lat") is not None and ev.get("lon") is not None:
            f.last_lat = float(ev["lat"])
            f.last_lon = float(ev["lon"])
        if ev.get("start"):
            f.last_timestamp = str(ev["start"])
        start, end = _parse_iso(ev.get("start")), _parse_iso(ev.get("end"))
        if start and end:
            f.loitering_duration_hours += (end - start).total_seconds() / 3600.0

    # --- GFW encounter events --------------------------------------------------
    for ev in encounter_events:
        key = _vessel_key_from_event(ev)
        if not key:
            continue
        f = get_or_create(key)
        f.encounter_count += 1
        f.sources.append("real_gfw_encounters")
        if ev.get("lat") is not None and ev.get("lon") is not None:
            f.last_lat = float(ev["lat"])
            f.last_lon = float(ev["lon"])
        if ev.get("start"):
            f.last_timestamp = str(ev["start"])

    # --- AISstream live positions: speed variance, heading-change, lane dev ---
    if aisstream_jsonl_paths:
        positions_by_vessel: dict[str, list[dict]] = defaultdict(list)
        for path in aisstream_jsonl_paths:
            if not Path(path).exists():
                continue
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg_type = rec.get("message_type") or rec.get("message", {}).get("MessageType")
                    if msg_type != "PositionReport":
                        continue
                    mmsi = rec.get("mmsi") or rec.get("message", {}).get("MetaData", {}).get("MMSI")
                    if mmsi is None:
                        continue
                    raw_msg = rec.get("raw") or rec.get("message") or {}
                    pr = (raw_msg.get("Message", {}) or {}).get("PositionReport", {}) or {}
                    meta = raw_msg.get("MetaData", {}) or {}
                    lat = pr.get("Latitude") if pr.get("Latitude") is not None else meta.get("latitude")
                    lon = pr.get("Longitude") if pr.get("Longitude") is not None else meta.get("longitude")
                    positions_by_vessel[str(mmsi)].append({
                        "t": rec.get("captured_at"),
                        "sog": pr.get("Sog"),
                        "cog": pr.get("Cog"),
                        "lat": lat,
                        "lon": lon,
                    })

        for key, positions in positions_by_vessel.items():
            positions.sort(key=lambda p: p.get("t") or "")
            sogs = [p["sog"] for p in positions if p.get("sog") is not None]
            cogs = [p["cog"] for p in positions if p.get("cog") is not None]
            lane_devs = [
                _distance_to_lane_km(p["lon"], p["lat"])
                for p in positions if p.get("lon") is not None and p.get("lat") is not None
            ]

            f = get_or_create(key)
            f.aisstream_position_count = len(positions)
            f.sources.append("real_aisstream_live")

            if len(sogs) >= 2:
                mean_sog = sum(sogs) / len(sogs)
                f.speed_variance = sum((s - mean_sog) ** 2 for s in sogs) / len(sogs)

            if len(cogs) >= 2:
                diffs = [_angle_diff_deg(cogs[i], cogs[i + 1]) for i in range(len(cogs) - 1)]
                f.heading_change_rate = sum(diffs) / len(diffs)

            if lane_devs:
                f.mean_lane_deviation_km = sum(lane_devs) / len(lane_devs)

    return features


def discover_aisstream_files(capture_dir: Path = AISSTREAM_CAPTURE_DIR) -> list[Path]:
    """
    Every day-rotated JSONL file captured so far — see aisstream_client.py.

    Fixed: previously defaulted to `Path("data/raw/aisstream_capture")`,
    resolved relative to CWD — which silently disagreed with
    aisstream_client.py's own (also-since-fixed) path resolution whenever
    this was called from a different working directory than the capture
    script was run from. Both now import the same constant from
    project_paths.py, so they can never drift apart again.
    """
    if not capture_dir.exists():
        return []
    files = sorted(set(list(capture_dir.glob("*.jsonl")) + list(capture_dir.glob("*.ndjson"))))
    return files
