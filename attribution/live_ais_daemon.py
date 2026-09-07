"""
attribution/live_ais_daemon.py — SIH26143 Attribution Subsystem

Persistent Live AIS Streamer & Local Spatial Database:
Connects to wss://stream.aisstream.io/v0/stream and continuously streams real-time
AIS position reports for vessels across the Indian EEZ and Arabian Sea corridor into
a local SQLite database (data/live_ais.db) with WAL mode and spatial-temporal indexing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

logger = logging.getLogger("live_ais_daemon")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"

# Project root resolution
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _PROJECT_ROOT / "data" / "live_ais.db"


def _get_con(db_path: Path = DB_PATH, timeout: float = 15.0) -> sqlite3.Connection:
    """Creates a connection configured with WAL mode and 10s busy timeout."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path), timeout=timeout)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=10000;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Initializes the SQLite database with WAL mode and indexes."""
    con = _get_con(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS ais_pings (
            mmsi TEXT,
            timestamp TEXT,
            lat REAL,
            lon REAL,
            sog REAL,
            cog REAL,
            heading REAL,
            ship_name TEXT,
            vessel_type INTEGER,
            PRIMARY KEY (mmsi, timestamp)
        );
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_ais_time_space ON ais_pings(timestamp, lat, lon);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ais_mmsi ON ais_pings(mmsi);")
    con.commit()
    return con


def insert_pings_batch(pings: List[Dict[str, Any]], db_path: Path = DB_PATH) -> int:
    """Inserts a batch of parsed AIS position reports into the database."""
    if not pings:
        return 0
    con = _get_con(db_path)
    try:
        cursor = con.cursor()
        cursor.executemany("""
            INSERT OR IGNORE INTO ais_pings 
            (mmsi, timestamp, lat, lon, sog, cog, heading, ship_name, vessel_type)
            VALUES (:mmsi, :timestamp, :lat, :lon, :sog, :cog, :heading, :ship_name, :vessel_type);
        """, pings)
        con.commit()
        return cursor.rowcount
    finally:
        con.close()


def query_vessels_in_window(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    start_time: str,
    end_time: str,
    db_path: Path = DB_PATH,
) -> List[Dict[str, Any]]:
    """Queries all AIS pings within the spatial-temporal window."""
    if not db_path.exists():
        return []
    con = _get_con(db_path)
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT mmsi, timestamp, lat, lon, sog, cog, heading, ship_name, vessel_type
            FROM ais_pings
            WHERE lon BETWEEN ? AND ?
              AND lat BETWEEN ? AND ?
              AND timestamp BETWEEN ? AND ?
            ORDER BY mmsi, timestamp ASC;
        """, (min_lon, max_lon, min_lat, max_lat, start_time, end_time))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def query_vessel_track(mmsi: str, start_time: str, end_time: str, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """Queries all AIS pings for a specific vessel MMSI."""
    if not db_path.exists():
        return []
    con = _get_con(db_path)
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT timestamp, lat, lon, sog, cog, heading, ship_name
            FROM ais_pings
            WHERE mmsi = ?
              AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC;
        """, (str(mmsi), start_time, end_time))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


async def run_ais_daemon(
    api_key: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    db_path: Path = DB_PATH,
    bounding_boxes: Optional[List[List[List[float]]]] = None,
):
    """
    Main asynchronous loop connecting to AISstream WebSocket.
    Automatically reconnects on disconnect with exponential backoff.
    """
    import websockets

    if not api_key:
        load_dotenv(_PROJECT_ROOT / ".env")
        api_key = os.getenv("AISSTREAM_API_KEY")

    if not api_key:
        logger.error("No AISSTREAM_API_KEY found in environment or .env file.")
        return

    init_db(db_path)

    # AISstream requires [[lat1, lon1], [lat2, lon2]] order
    if not bounding_boxes:
        bounding_boxes = [
            [[10.0, 60.0], [25.0, 78.0]]  # Arabian Sea & Indian EEZ
        ]

    subscribe_msg = {
        "APIKey": api_key,
        "BoundingBoxes": bounding_boxes,
        "FilterMessageTypes": ["PositionReport"],
    }

    start_loop = datetime.now(timezone.utc)
    batch: List[Dict[str, Any]] = []
    backoff = 2

    logger.info("Starting Persistent Live AIS Streamer for Indian EEZ (%s)...", db_path)

    while True:
        try:
            async with websockets.connect(AISSTREAM_URL, ping_interval=20, ping_timeout=20) as ws:
                logger.info("Connected to AISstream.io! Sending subscription message...")
                await ws.send(json.dumps(subscribe_msg))
                backoff = 2  # Reset backoff on successful connection

                while True:
                    if duration_seconds:
                        elapsed = (datetime.now(timezone.utc) - start_loop).total_seconds()
                        if elapsed >= duration_seconds:
                            if batch:
                                insert_pings_batch(batch, db_path)
                            logger.info("AIS daemon completed requested duration of %ds.", duration_seconds)
                            return

                    msg_raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    msg = json.loads(msg_raw)

                    msg_type = msg.get("MessageType")
                    meta = msg.get("MetaData", {})
                    pos_data = msg.get("Message", {}).get("PositionReport", {})

                    if msg_type == "PositionReport" and pos_data:
                        mmsi = str(meta.get("MMSI") or pos_data.get("UserID", ""))
                        ts = meta.get("time_utc") or datetime.now(timezone.utc).isoformat()
                        lat = float(pos_data.get("Latitude") if pos_data.get("Latitude") is not None else meta.get("latitude", 0.0))
                        lon = float(pos_data.get("Longitude") if pos_data.get("Longitude") is not None else meta.get("longitude", 0.0))
                        sog = float(pos_data.get("Sog", 0.0))
                        cog = float(pos_data.get("Cog", 0.0))
                        heading = float(pos_data.get("TrueHeading", 511.0))
                        ship_name = str(meta.get("ShipName", "")).strip()

                        if mmsi and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat != 0.0 or lon != 0.0):
                            batch.append({
                                "mmsi": mmsi,
                                "timestamp": ts,
                                "lat": lat,
                                "lon": lon,
                                "sog": sog,
                                "cog": cog,
                                "heading": heading,
                                "ship_name": ship_name,
                                "vessel_type": None,
                            })

                    if len(batch) >= 20:
                        inserted = insert_pings_batch(batch, db_path)
                        logger.debug("Committed %d AIS pings to %s", inserted, db_path.name)
                        batch.clear()

        except asyncio.CancelledError:
            if batch:
                insert_pings_batch(batch, db_path)
            logger.info("AIS daemon shutdown gracefully.")
            break
        except Exception as e:
            logger.warning("AISstream connection dropped (%s). Reconnecting in %ds...", e, backoff)
            if batch:
                insert_pings_batch(batch, db_path)
                batch.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OilTrace Persistent Live AIS Streamer")
    parser.add_argument("--duration", type=int, default=None, help="Run duration in seconds (default runs indefinitely)")
    args = parser.parse_args()

    try:
        asyncio.run(run_ais_daemon(duration_seconds=args.duration))
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
