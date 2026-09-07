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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from .project_paths import AISSTREAM_CAPTURE_DIR
except ImportError:
    from project_paths import AISSTREAM_CAPTURE_DIR

try:
    from .route_reconstruction import get_flag_risk_prior
except ImportError:
    try:
        from route_reconstruction import get_flag_risk_prior
    except ImportError:
        def get_flag_risk_prior(flag_code):
            return 0.35  # fallback default

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
    gap_count: float = 0.0
    gap_duration_hours: float = 0.0
    loitering_count: float = 0.0
    loitering_duration_hours: float = 0.0
    encounter_count: float = 0.0
    speed_variance: Optional[float] = None
    heading_change_rate: Optional[float] = None  # mean abs deg change per position update
    mean_lane_deviation_km: Optional[float] = None
    # --- 5 NEW FEATURES (14-feature expansion, Project Doc Section 6.2–6.3) ---
    discharge_speed_fraction: float = 0.0       # Fraction of voyage at 4.0–8.0 kn (MARPOL Annex I bilge dumping window)
    nighttime_gap_ratio: float = 0.0            # Ratio of AIS gaps during 18:00–06:00 local solar time
    temporal_proximity_hours: Optional[float] = None   # Hours between vessel CPA and estimated spill time
    track_intersection_score: float = 0.0       # 4D spatio-temporal ray-trace score from route_reconstruction.py
    port_risk_prior: float = 0.20               # Flag-of-convenience / high-risk registry prior (Paris MoU)
    # --- Causal flag from route reconstruction ---
    proximate_but_absent_at_origin: bool = False  # True if vessel is near slick now but was absent at origin during release
    # --- Position & metadata ---
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    last_timestamp: Optional[str] = None
    aisstream_position_count: int = 0
    vessel_flag: Optional[str] = None           # ISO 3166-1 alpha-3 flag code (for port_risk_prior lookup)
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
            "discharge_speed_fraction": round(self.discharge_speed_fraction, 4),
            "nighttime_gap_ratio": round(self.nighttime_gap_ratio, 4),
            "temporal_proximity_hours": self.temporal_proximity_hours,
            "track_intersection_score": round(self.track_intersection_score, 4),
            "port_risk_prior": round(self.port_risk_prior, 4),
            "proximate_but_absent_at_origin": self.proximate_but_absent_at_origin,
            "last_lat": self.last_lat,
            "last_lon": self.last_lon,
            "last_timestamp": self.last_timestamp,
            "aisstream_position_count": self.aisstream_position_count,
            "vessel_flag": self.vessel_flag,
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
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _event_weight(event_dt: Optional[datetime], spill_dt: Optional[datetime]) -> float:
    if not event_dt or not spill_dt:
        return 1.0
    if event_dt.tzinfo is not None:
        event_dt = event_dt.replace(tzinfo=None)
    if spill_dt.tzinfo is not None:
        spill_dt = spill_dt.replace(tzinfo=None)
    diff_hours = abs((event_dt - spill_dt).total_seconds()) / 3600.0
    return math.exp(-diff_hours / 12.0)

def _update_temporal_prox(f: VesselFeatures, event_dt: Optional[datetime], spill_dt: Optional[datetime]):
    if not event_dt or not spill_dt:
        return
    if event_dt.tzinfo is not None:
        event_dt = event_dt.replace(tzinfo=None)
    if spill_dt.tzinfo is not None:
        spill_dt = spill_dt.replace(tzinfo=None)
    diff_hours = abs((event_dt - spill_dt).total_seconds()) / 3600.0
    if f.temporal_proximity_hours is None or diff_hours < f.temporal_proximity_hours:
        f.temporal_proximity_hours = diff_hours

def build_features(
    presence_entries: list[dict],
    gap_events: list[dict],
    loitering_events: list[dict],
    encounter_events: list[dict],
    aisstream_jsonl_paths: Optional[list[Path]] = None,
    spill_time: Optional[str] = None,
) -> dict[str, VesselFeatures]:
    """
    Merge every real source keyed by vessel (ssvid/MMSI as string). Returns
    a dict of vessel_key -> VesselFeatures. Callers should treat any `None`
    field as genuinely missing, not zero.
    """
    features: dict[str, VesselFeatures] = {}
    spill_dt = _parse_iso(spill_time) if spill_time else None

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
        event_dt = _parse_iso(rec.get("date") or rec.get("entryTimestamp"))
        weight = _event_weight(event_dt, spill_dt)
        if hours is not None:
            presence_hours_by_vessel[key] += float(hours) * weight
        f = get_or_create(key)
        _update_temporal_prox(f, event_dt, spill_dt)
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
    nighttime_gap_counts: dict[str, int] = defaultdict(int)
    total_gap_counts: dict[str, int] = defaultdict(int)
    for ev in gap_events:
        key = _vessel_key_from_event(ev)
        if not key:
            continue
        f = get_or_create(key)
        
        event_dt = _parse_iso(ev.get("start"))
        weight = _event_weight(event_dt, spill_dt)
        _update_temporal_prox(f, event_dt, spill_dt)

        f.gap_count += 1.0 * weight
        f.sources.append("real_gfw_gaps")
        
        # Extract vessel flag from event metadata for port_risk_prior
        vessel_meta = ev.get("vessel", {}) or {}
        if vessel_meta.get("flag") and not f.vessel_flag:
            f.vessel_flag = str(vessel_meta["flag"])
        
        pos = ev.get("position") or {}
        if pos.get("lat") is not None and pos.get("lon") is not None:
            f.last_lat = float(pos["lat"])
            f.last_lon = float(pos["lon"])
        if ev.get("start"):
            f.last_timestamp = str(ev["start"])
        start, end = _parse_iso(ev.get("start")), _parse_iso(ev.get("end"))
        if start and end:
            f.gap_duration_hours += ((end - start).total_seconds() / 3600.0) * weight
        
        # Nighttime gap tracking: approximate local solar time from longitude
        # Local solar time ≈ UTC + (longitude / 15) hours
        total_gap_counts[key] += 1
        if event_dt:
            gap_lon = float(pos["lon"]) if pos.get("lon") is not None else (f.last_lon or 72.0)
            utc_offset_hours = gap_lon / 15.0
            local_hour = (event_dt.hour + utc_offset_hours) % 24
            if local_hour >= 18.0 or local_hour < 6.0:
                nighttime_gap_counts[key] += 1
    
    # Compute nighttime_gap_ratio for all vessels with gaps
    for key in total_gap_counts:
        if total_gap_counts[key] > 0:
            features[key].nighttime_gap_ratio = nighttime_gap_counts[key] / total_gap_counts[key]

    # --- GFW loitering events -------------------------------------------------
    for ev in loitering_events:
        key = _vessel_key_from_event(ev)
        if not key:
            continue
        f = get_or_create(key)
        
        event_dt = _parse_iso(ev.get("start"))
        weight = _event_weight(event_dt, spill_dt)
        _update_temporal_prox(f, event_dt, spill_dt)

        f.loitering_count += 1.0 * weight
        f.sources.append("real_gfw_loitering")
        pos = ev.get("position") or {}
        if pos.get("lat") is not None and pos.get("lon") is not None:
            f.last_lat = float(pos["lat"])
            f.last_lon = float(pos["lon"])
        if ev.get("start"):
            f.last_timestamp = str(ev["start"])
        start, end = _parse_iso(ev.get("start")), _parse_iso(ev.get("end"))
        if start and end:
            f.loitering_duration_hours += ((end - start).total_seconds() / 3600.0) * weight

    # --- GFW encounter events --------------------------------------------------
    for ev in encounter_events:
        key = _vessel_key_from_event(ev)
        if not key:
            continue
        f = get_or_create(key)
        
        event_dt = _parse_iso(ev.get("start"))
        weight = _event_weight(event_dt, spill_dt)
        _update_temporal_prox(f, event_dt, spill_dt)

        f.encounter_count += 1.0 * weight
        f.sources.append("real_gfw_encounters")
        pos = ev.get("position") or {}
        if pos.get("lat") is not None and pos.get("lon") is not None:
            f.last_lat = float(pos["lat"])
            f.last_lon = float(pos["lon"])
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

        # Also ingest live AIS pings from persistent SQLite database if present
        db_file = Path(__file__).resolve().parent.parent / "data" / "live_ais.db"
        if db_file.exists():
            try:
                import sqlite3
                con = sqlite3.connect(str(db_file))
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("SELECT mmsi, timestamp, lat, lon, sog, cog FROM ais_pings")
                for r in cur.fetchall():
                    mmsi_str = str(r["mmsi"])
                    positions_by_vessel[mmsi_str].append({
                        "t": r["timestamp"],
                        "sog": r["sog"],
                        "cog": r["cog"],
                        "lat": r["lat"],
                        "lon": r["lon"],
                    })
                con.close()
            except Exception:
                pass

        for key, positions in positions_by_vessel.items():
            positions.sort(key=lambda p: p.get("t") or "")
            f = get_or_create(key)
            for p in positions:
                _update_temporal_prox(f, _parse_iso(p.get("t")), spill_dt)
            
            sogs = [p["sog"] for p in positions if p.get("sog") is not None]
            cogs = [p["cog"] for p in positions if p.get("cog") is not None]
            lane_devs = [
                _distance_to_lane_km(p["lon"], p["lat"])
                for p in positions if p.get("lon") is not None and p.get("lat") is not None
            ]

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

            # NEW: discharge_speed_fraction — fraction of pings at 4.0–8.0 kn
            # (MARPOL Annex I bilge dumping window, Project Doc Section 6.2)
            if sogs:
                discharge_count = sum(1 for s in sogs if 4.0 <= s <= 8.0)
                f.discharge_speed_fraction = discharge_count / len(sogs)

    # --- Post-merge: compute port_risk_prior from vessel flag ------------------
    # Uses Paris MoU flag-of-convenience risk data from route_reconstruction.py.
    # Flag codes are extracted from GFW event metadata (gap/loitering/encounter
    # events carry vessel.flag) during the processing above.
    for key, f in features.items():
        if f.vessel_flag:
            f.port_risk_prior = get_flag_risk_prior(f.vessel_flag)

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
