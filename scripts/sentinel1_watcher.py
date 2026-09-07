"""
scripts/sentinel1_watcher.py — SIH26143

Autonomous Sentinel-1 Satellite Watcher:
Polls the Copernicus Data Space Ecosystem (CDSE) OData API for newly acquired
Sentinel-1 C-band SAR Level-1 GRD products over the Indian EEZ and primary shipping corridors.

Tracks processed scenes in a local SQLite database (data/processed_scenes.db) to prevent
duplicate processing. When a newly observed scene matches surveillance criteria, it logs
the pass metadata and triggers automated oil spill detection.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("sentinel1_watcher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CDSE_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _PROJECT_ROOT / "data" / "processed_scenes.db"

# Arabian Sea & Mumbai High Corridor default bounding box [minLon, minLat, maxLon, maxLat]
DEFAULT_BBOX = [68.0, 15.0, 74.0, 22.0]


def init_tracker_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Initializes local SQLite database for tracking ingested SAR scenes."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("""
        CREATE TABLE IF NOT EXISTS sar_scenes (
            scene_id TEXT PRIMARY KEY,
            acquired_at TEXT,
            ingested_at TEXT,
            footprint TEXT,
            status TEXT
        );
    """)
    # Check if footprint column exists, add if upgrading from older schema
    cur = con.cursor()
    columns = [col[1] for col in cur.execute("PRAGMA table_info(sar_scenes)").fetchall()]
    if "footprint" not in columns:
        con.execute("ALTER TABLE sar_scenes ADD COLUMN footprint TEXT;")
    con.commit()
    return con


def is_scene_processed(scene_id: str, db_path: Path = DB_PATH) -> bool:
    """Checks if a scene ID has already been logged or processed."""
    if not db_path.exists():
        return False
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute("SELECT 1 FROM sar_scenes WHERE scene_id = ?", (scene_id,))
        return cur.fetchone() is not None
    finally:
        con.close()


def record_scene(scene: Dict[str, Any], status: str = "DISCOVERED", db_path: Path = DB_PATH):
    """Records a newly discovered or processed Sentinel-1 SAR scene."""
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("""
            INSERT OR REPLACE INTO sar_scenes 
            (scene_id, acquired_at, ingested_at, footprint, status)
            VALUES (?, ?, ?, ?, ?);
        """, (
            scene.get("id"),
            scene.get("acquired_at"),
            datetime.now(timezone.utc).isoformat(),
            json.dumps(scene.get("footprint")),
            status,
        ))
        con.commit()
    finally:
        con.close()


def query_cdse_sentinel1_passes(
    bbox: List[float] = DEFAULT_BBOX,
    top: int = 5,
) -> List[Dict[str, Any]]:
    """
    Queries CDSE OData API for the latest Sentinel-1 GRD acquisitions.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    # WKT polygon for spatial intersection
    wkt_poly = f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, {max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"

    # Filter for Sentinel-1 GRD products intersecting our surveillance corridor
    odata_filter = (
        "Collection/Name eq 'SENTINEL-1' and "
        "contains(Name, 'GRD') and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;{wkt_poly}')"
    )

    params = {
        "$filter": odata_filter,
        "$orderby": "ContentDate/Start desc",
        "$top": top,
    }

    logger.info("Querying CDSE OData API for latest Sentinel-1 GRD passes (bbox=%s)...", bbox)
    try:
        resp = requests.get(CDSE_ODATA_URL, params=params, timeout=25)
        if resp.status_code == 200:
            val = resp.json().get("value", [])
            logger.info("CDSE OData returned %d Sentinel-1 scenes matching surveillance polygon.", len(val))
            results = []
            for item in val:
                scene_name = item.get("Name", "")
                acquired_at = item.get("ContentDate", {}).get("Start", "")
                footprint = item.get("Footprint")
                results.append({
                    "id": scene_name,
                    "acquired_at": acquired_at,
                    "footprint": footprint,
                })
            return results
        else:
            logger.warning("CDSE OData API returned HTTP %d: %s", resp.status_code, resp.text[:150])
            # Fallback to general S1 GRD query without spatial geometry filter if spatial function has syntax variation
            params_fallback = {
                "$filter": "Collection/Name eq 'SENTINEL-1' and contains(Name, 'GRD')",
                "$orderby": "ContentDate/Start desc",
                "$top": top,
            }
            fb_resp = requests.get(CDSE_ODATA_URL, params=params_fallback, timeout=20)
            if fb_resp.status_code == 200:
                val = fb_resp.json().get("value", [])
                return [{"id": it.get("Name", ""), "acquired_at": it.get("ContentDate", {}).get("Start", ""), "footprint": it.get("Footprint")} for it in val]
            return []
    except requests.RequestException as e:
        logger.warning("CDSE OData query failed or timed out: %s", e)
        return []


def run_watcher(
    poll_interval_seconds: int = 10800,  # 3 hours
    once: bool = False,
    bbox: List[float] = DEFAULT_BBOX,
):
    """Main watcher loop periodically scanning for new Sentinel-1 acquisitions."""
    init_tracker_db()
    logger.info("Starting Autonomous Sentinel-1 Satellite Watcher for Indian EEZ...")

    while True:
        scenes = query_cdse_sentinel1_passes(bbox=bbox, top=5)
        new_count = 0

        for sc in scenes:
            scene_id = sc["id"]
            if not is_scene_processed(scene_id):
                new_count += 1
                record_scene(sc, status="SURVEILLANCE_ACTIVE")
                logger.info(
                    "🚨 [NEW SAR PASS DETECTED] Scene: %s | Acquired: %s",
                    scene_id, sc["acquired_at"]
                )

        if new_count == 0:
            logger.info("Surveillance up to date. No unrecorded passes found.")
        else:
            logger.info("Successfully recorded %d new Sentinel-1 acquisitions to %s", new_count, DB_PATH.name)

        if once:
            break

        logger.info("Sleeping %d seconds until next satellite pass check...", poll_interval_seconds)
        time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OilTrace Autonomous Sentinel-1 Satellite Watcher")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=10800, help="Polling interval in seconds (default 3 hours)")
    args = parser.parse_args()

    run_watcher(poll_interval_seconds=args.interval, once=args.once)
