"""
backend/app/routers/live_feed.py — SIH26143

Live Surveillance & Telemetry Router:
Provides a real-time WebSocket connection (/ws/live-ais) broadcasting live AIS position reports
from the persistent AIS streamer to frontend map visualizers, and an endpoint querying newly
acquired Sentinel-1 satellite passes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..db import sqlite_connection

logger = logging.getLogger("live_feed_router")
router = APIRouter(tags=["surveillance"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LIVE_AIS_DB = _PROJECT_ROOT / "data" / "live_ais.db"
SCENES_DB = _PROJECT_ROOT / "data" / "processed_scenes.db"


class ConnectionManager:
    """Manages active frontend WebSocket subscribers."""
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("[ws] New client connected (total: %d)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info("[ws] Client disconnected (remaining: %d)", len(self.active_connections))

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        dead_conns = []
        payload = json.dumps(message)
        # Snapshot active connections to avoid RuntimeError: Set changed size during iteration
        for conn in list(self.active_connections):
            try:
                await conn.send_text(payload)
            except Exception:
                dead_conns.append(conn)
        for dead in dead_conns:
            self.disconnect(dead)


manager = ConnectionManager()


@router.websocket("/ws/live-ais")
async def websocket_live_ais_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint streaming real-time AIS vessel telemetry to the frontend.
    Pushes newly received position reports every 2 seconds.
    """
    await manager.connect(websocket)
    last_timestamp = datetime.now(timezone.utc).isoformat()

    initial_push = True

    async def _client_receiver():
        try:
            while True:
                msg_text = await websocket.receive_text()
                try:
                    data = json.loads(msg_text)
                    if data.get("type") == "ping":
                        pong_msg = {
                            "type": "pong",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "sequence_id": data.get("sequence_id"),
                        }
                        await websocket.send_text(json.dumps(pong_msg))
                except Exception:
                    pass
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    receiver_task = asyncio.create_task(_client_receiver())
    try:
        while True:
            new_pings = []
            if LIVE_AIS_DB.exists():
                def _read_ais_db(is_initial: bool, last_ts: str):
                    """Blocking SQLite read, wrapped in threadpool so it doesn't block asyncio."""
                    result_rows = []
                    new_last_ts = last_ts
                    try:
                        with sqlite_connection(LIVE_AIS_DB) as con:
                            cur = con.cursor()
                            if is_initial:
                                cur.execute("""
                                    SELECT mmsi, timestamp, lat, lon, sog, cog, heading, ship_name
                                    FROM ais_pings
                                    ORDER BY timestamp DESC
                                    LIMIT 30;
                                """)
                                rows = cur.fetchall()
                                if rows:
                                    result_rows = [dict(r) for r in rows]
                                    new_last_ts = max(r["timestamp"] for r in rows)
                            else:
                                cur.execute("""
                                    SELECT mmsi, timestamp, lat, lon, sog, cog, heading, ship_name
                                    FROM ais_pings
                                    WHERE timestamp > ?
                                    ORDER BY timestamp ASC
                                    LIMIT 50;
                                """, (last_ts,))
                                rows = cur.fetchall()
                                for r in rows:
                                    result_rows.append(dict(r))
                                    new_last_ts = r["timestamp"]
                    except Exception as e:
                        logger.debug("[ws] Database read error: %s", e)
                    return result_rows, new_last_ts

                # A9 FIX: Run blocking SQLite I/O in a thread pool so the asyncio event loop
                # is not blocked during DB reads (which can freeze all WebSocket connections).
                from starlette.concurrency import run_in_threadpool
                result_pings, last_timestamp = await run_in_threadpool(
                    _read_ais_db, initial_push, last_timestamp
                )
                new_pings = result_pings
                if initial_push and result_pings:
                    initial_push = False

            # If live database has no new updates, send active telemetry heartbeat with simulated step
            if not new_pings:
                now_str = datetime.now(timezone.utc).isoformat()
                heartbeat_msg = {
                    "type": "heartbeat",
                    "timestamp": now_str,
                    "active_surveillance_zone": "Mumbai-Gulf Energy Corridor",
                    "coverage_status": "ACTIVE_SURVEILLANCE",
                }
                await websocket.send_text(json.dumps(heartbeat_msg))
            else:
                msg = {
                    "type": "ais_batch",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "pings_count": len(new_pings),
                    "pings": new_pings,
                }
                await websocket.send_text(json.dumps(msg))

            await asyncio.sleep(2.0)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.debug("[ws] Stream terminated: %s", e)
        manager.disconnect(websocket)
    finally:
        receiver_task.cancel()
        try:
            await receiver_task
        except (asyncio.CancelledError, Exception):
            pass


@router.get("/api/surveillance/satellite-passes")
async def get_satellite_passes() -> dict:
    """Returns all newly acquired Sentinel-1 SAR passes logged by the satellite watcher."""
    if not SCENES_DB.exists():
        return {"total_passes": 0, "passes": []}
    try:
        with sqlite_connection(SCENES_DB) as con:
            cur = con.cursor()
            cur.execute("""
                SELECT scene_id, acquired_at, ingested_at, status
                FROM sar_scenes
                ORDER BY acquired_at DESC
                LIMIT 20;
            """)
            rows = cur.fetchall()
            passes = [dict(r) for r in rows]
            return {
                "total_passes": len(passes),
                "surveillance_zone": "Indian Exclusive Economic Zone (EEZ)",
                "passes": passes,
            }
    except Exception as e:
        logger.warning("Failed querying satellite scenes DB: %s", e)
        return {"total_passes": 0, "passes": []}
