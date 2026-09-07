"""
scripts/seed_live_ais.py — SIH26143
Seeds data/live_ais.db with realistic AIS position reports for Mumbai-Gulf and
Arabian Sea vessels so the live WebSocket radar (/ws/live-ais) broadcasts active
vessel telemetry to the frontend.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = Path("c:/WORK/OilTrace").resolve()
DB_PATH = PROJECT_ROOT / "data" / "live_ais.db"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=15.0)
    cur = con.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA busy_timeout=10000;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA foreign_keys=ON;")
    cur.execute("""
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ais_time_space ON ais_pings(timestamp, lat, lon);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ais_mmsi ON ais_pings(mmsi);")

    # Collect vessels from scenarios
    vessels = [
        {"mmsi": "419001415", "name": "TRIDENT II (SUSPECT VLCC)", "lon": 72.35, "lat": 18.75, "sog": 6.4, "cog": 42.0},
        {"mmsi": "419702000", "name": "KAVERI STAR", "lon": 72.48, "lat": 18.90, "sog": 12.8, "cog": 180.0},
        {"mmsi": "419900753", "name": "BLUE MARLIN", "lon": 72.10, "lat": 18.60, "sog": 14.2, "cog": 135.0},
        {"mmsi": "636022539", "name": "PACIFIC PIONEER", "lon": 71.95, "lat": 18.45, "sog": 16.0, "cog": 290.0},
        {"mmsi": "636018911", "name": "AL JABAL (VLCC)", "lon": 69.45, "lat": 22.38, "sog": 5.8, "cog": 65.0},
        {"mmsi": "538007122", "name": "PACIFIC VOYAGER", "lon": 69.55, "lat": 22.42, "sog": 11.5, "cog": 80.0},
        {"mmsi": "477123456", "name": "STAR SHENZHEN", "lon": 73.45, "lat": 15.48, "sog": 7.2, "cog": 340.0},
        {"mmsi": "419001999", "name": "MORMUGAO EXPLORER", "lon": 73.55, "lat": 15.52, "sog": 10.4, "cog": 160.0},
        {"mmsi": "353136000", "name": "EVER GIVEN", "lon": 66.25, "lat": 17.88, "sog": 18.5, "cog": 275.0},
        {"mmsi": "412000001", "name": "AL-MANAR", "lon": 72.40, "lat": 18.80, "sog": 6.8, "cog": 50.0},
    ]

    now_utc = datetime.now(timezone.utc)
    inserted_count = 0

    for v in vessels:
        # Generate 10 pings per vessel over the last hour
        for step in range(10):
            p_time = now_utc - timedelta(minutes=(9 - step) * 6)
            # Drift position forward along course
            dist_nm = (v["sog"] * (step * 6.0) / 60.0)
            d_lat = (dist_nm / 60.0) * 0.5
            d_lon = (dist_nm / 60.0) * 0.5
            
            p_lat = round(v["lat"] + d_lat, 5)
            p_lon = round(v["lon"] + d_lon, 5)
            
            cur.execute("""
                INSERT OR REPLACE INTO ais_pings 
                (mmsi, timestamp, lat, lon, sog, cog, heading, ship_name, vessel_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                v["mmsi"],
                p_time.isoformat(),
                p_lat,
                p_lon,
                v["sog"],
                v["cog"],
                v["cog"],
                v["name"],
                80 if "Tanker" in v["name"] or "VLCC" in v["name"] else 70,
            ))
            inserted_count += 1

    con.commit()
    con.close()
    print(f"[seed_live_ais] Successfully seeded {inserted_count} AIS pings into {DB_PATH}")

if __name__ == "__main__":
    main()
