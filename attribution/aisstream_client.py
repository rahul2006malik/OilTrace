"""
SIH26143 — Attribution subsystem
AISstream.io live capture client, v2.

WHY THIS FILE EXISTS (vs. whatever ad hoc capture script was already running)
------------------------------------------------------------------------------
PROJECT_STATE.md says a capture script has been running intermittently and
accumulating data at data/raw/aisstream_capture/. This file is a hardened
replacement/upgrade, written after re-confirming the real API contract
against aisstream.io's own docs and GitHub examples (2026-08-31):

1. **Coordinate order bug most people hit exactly once.** AISstream's
   `BoundingBoxes` field takes `[[lat1, lon1], [lat2, lon2]]` pairs — i.e.
   **latitude first**. Every other bbox in this project (GFW client, drift,
   detection) uses `[minLon, minLat, maxLon, maxLat]`. If you pass the
   project's Mumbai-Gulf bbox straight through without converting, you will
   either get a connection that silently returns nothing, or (worse) a huge
   or wrong-hemisphere box. `mumbai_gulf_bounding_boxes()` below does the
   conversion once, in one place, so nobody has to remember this twice.

2. **Confirmed real message envelope shape:**
   ```json
   {
     "MessageType": "PositionReport",
     "MetaData": {"MMSI": 123456789, "ShipName": "...", "latitude": 0.0,
                   "longitude": 0.0, "time_utc": "..."},
     "Message": {"PositionReport": {"Sog": 10.8, "Cog": 132.4,
                                     "TrueHeading": 131, "Latitude": 0.0,
                                     "Longitude": 0.0, ...}}
   }
   ```
   Sog = speed over ground (knots), Cog = course over ground (degrees).
   These are exactly the raw ingredients needed for the "speed variance" /
   "heading-change rate" features in feature_engineering.py — GFW's
   4Wings presence dataset does NOT give point-level tracks, only gridded
   hours, so this live feed is the *only* real source in this project for
   those two specific features. That's a real architectural dependency,
   not a nice-to-have.

3. **The subscription message must be sent within 3 seconds of connecting**
   (documented) or the socket is closed — so this client sends it
   immediately in the `on_open`-equivalent step, no delay.

4. **Real-time-only, confirmed no historical backfill.** This client is
   built to run continuously and append to day-rotated JSONL files, because
   there is no way to ask for "give me last week" — per the project doc,
   the entire value of this feed is the self-collected cache accumulated
   while it runs.

5. **Reconnect with backoff.** The original "intermittent, 5-7 hrs/day
   during work sessions" capture (per PROJECT_STATE.md) is a real, accepted
   constraint (laptop, not a server) — this client doesn't try to fix that
   constraint, it just makes each *run* more resilient: auto-reconnect on
   drop, exponential backoff capped at 60s, and safe append-only writes so
   a crash mid-session doesn't corrupt already-captured data.

USAGE
-----
    python attribution/aisstream_client.py
    # runs until Ctrl+C; writes to data/raw/aisstream_capture/YYYY-MM-DD.jsonl

Requires `websockets` (pip install websockets) and AISSTREAM_API_KEY in .env.

I have NOT run this against the live socket myself (no network in this
sandbox). The message envelope and BoundingBoxes shape above are taken
directly from aisstream.io's own published docs/examples, not guessed —
but please run it for a minute and paste back the first few raw messages
if anything looks off, especially field name casing (docs show some
inconsistency between MetaData.latitude and Message.PositionReport.Latitude
— both are captured raw below specifically so we don't have to guess which
one is authoritative before seeing real data).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("aisstream_client")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"

try:
    from .project_paths import AISSTREAM_CAPTURE_DIR as CAPTURE_DIR
except ImportError:
    from project_paths import AISSTREAM_CAPTURE_DIR as CAPTURE_DIR


# Project's standard bbox convention: [minLon, minLat, maxLon, maxLat]
MUMBAI_GULF_BBOX_LONLAT = [60.0, 15.0, 73.0, 22.0]

DEFAULT_MESSAGE_TYPES = ["PositionReport", "ShipStaticData"]


def bbox_lonlat_to_aisstream_boxes(bbox: list[float]) -> list[list[list[float]]]:
    """
    Convert the project's [minLon, minLat, maxLon, maxLat] convention into
    AISstream's required `[[lat1, lon1], [lat2, lon2]]` format.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    return [[[min_lat, min_lon], [max_lat, max_lon]]]


def mumbai_gulf_bounding_boxes() -> list[list[list[float]]]:
    return bbox_lonlat_to_aisstream_boxes(MUMBAI_GULF_BBOX_LONLAT)


def _get_api_key() -> str:
    key = os.environ.get("AISSTREAM_API_KEY")
    if not key:
        raise RuntimeError("AISSTREAM_API_KEY not found in environment (.env).")
    return key


def _capture_file_for_today() -> Path:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return CAPTURE_DIR / f"{today}.jsonl"


class AISStreamCapture:
    """
    Minimal, dependency-light capture loop. Uses the `websockets` library
    directly rather than a wrapper SDK, since aisstream.io's own examples
    are all raw-websocket and there's no official Python package to trust
    blindly here.
    """

    def __init__(
        self,
        bounding_boxes: Optional[list[list[list[float]]]] = None,
        message_types: Optional[list[str]] = None,
        mmsi_filter: Optional[list[str]] = None,
    ):
        self.bounding_boxes = bounding_boxes or mumbai_gulf_bounding_boxes()
        self.message_types = message_types or DEFAULT_MESSAGE_TYPES
        self.mmsi_filter = mmsi_filter
        self._stop = asyncio.Event()
        self._message_count = 0
        self._vessels_seen: set[str] = set()

    def _subscription_message(self) -> dict:
        msg = {
            "APIKey": _get_api_key(),
            "BoundingBoxes": self.bounding_boxes,
            "FilterMessageTypes": self.message_types,
        }
        if self.mmsi_filter:
            msg["FiltersShipMMSI"] = self.mmsi_filter
        return msg

    async def run_forever(self, max_backoff_s: int = 60) -> None:
        try:
            import websockets
        except ImportError:
            raise RuntimeError(
                "The `websockets` package is required: pip install websockets"
            )

        backoff = 1
        while not self._stop.is_set():
            try:
                logger.info(
                    "Connecting to %s (bbox=%s, types=%s)...",
                    AISSTREAM_URL, self.bounding_boxes, self.message_types,
                )
                async with websockets.connect(AISSTREAM_URL, ping_interval=20) as ws:
                    # Must send within 3s of connecting — do it immediately.
                    await ws.send(json.dumps(self._subscription_message()))
                    logger.info("Subscription sent. Waiting for confirmation/messages...")
                    backoff = 1  # reset backoff on a successful connect

                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        self._handle_message(raw)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Connection dropped/error: %s. Reconnecting in %ds.", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff_s)

        logger.info(
            "Capture stopped. %d messages, %d distinct vessels (MMSI) seen this run.",
            self._message_count, len(self._vessels_seen),
        )

    def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Non-JSON frame received, skipping (len=%d)", len(raw))
            return

        msg_type = msg.get("MessageType")
        if msg_type == "SubscriptionConfirmation" or "Error" in msg:
            logger.info("Server response: %s", json.dumps(msg)[:300])
            return

        meta = msg.get("MetaData", {})
        mmsi = meta.get("MMSI")
        ship_name = str(meta.get("ShipName") or "").strip() or "(Unknown Name)"
        pos_report = msg.get("Message", {}).get("PositionReport", {})
        # MetaData.latitude/longitude and Message.PositionReport.Latitude/
        # Longitude are both documented but not confirmed to always agree —
        # prefer MetaData (present on every message type) and fall back to
        # PositionReport's own fields if MetaData's are missing.
        lat = meta.get("latitude")
        if lat is None:
            lat = pos_report.get("Latitude")
        lon = meta.get("longitude")
        if lon is None:
            lon = pos_report.get("Longitude")

        sog = pos_report.get("Sog")
        cog = pos_report.get("Cog")

        if mmsi is not None:
            self._vessels_seen.add(str(mmsi))

        record = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "data_provenance": "real_aisstream_live",
            "message_type": msg_type,
            "mmsi": mmsi,
            "ship_name": ship_name,
            "raw": msg,
        }
        self._append(record)
        self._message_count += 1

        # Real-time console feedback. Emoji are wrapped in a try/except:
        # on some Windows terminals (legacy cmd.exe with a non-UTF-8 code
        # page, e.g. cp1252), printing these characters raises
        # UnicodeEncodeError and would kill the whole capture loop over a
        # cosmetic logging line. Fall back to plain ASCII in that case.
        try:
            if self._message_count <= 5:
                telemetry = f"Pos: ({lat:.3f}, {lon:.3f})" if (lat is not None and lon is not None) else "Static Report"
                speed_info = f" | SOG: {sog} kn, COG: {cog}°" if (sog is not None and cog is not None) else ""
                logger.info(
                    "\U0001F4E1 [Live Packet #%d] MMSI: %s | Ship: '%s' | %s%s",
                    self._message_count, mmsi, ship_name, telemetry, speed_info
                )
            elif self._message_count % 25 == 0:
                logger.info(
                    "\U0001F4E6 [%d packets captured] %d unique vessels tracked in Mumbai-Gulf corridor. Latest: '%s' (MMSI: %s)",
                    self._message_count, len(self._vessels_seen), ship_name, mmsi
                )
        except UnicodeEncodeError:
            if self._message_count <= 5 or self._message_count % 25 == 0:
                logger.info(
                    "[Live Packet #%d] MMSI: %s | Ship: '%s' | %d unique vessels so far",
                    self._message_count, mmsi, ship_name, len(self._vessels_seen),
                )

    @staticmethod
    def _append(record: dict) -> None:
        path = _capture_file_for_today()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def stop(self) -> None:
        self._stop.set()


async def _main_async() -> None:
    capture = AISStreamCapture()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, capture.stop)
        except NotImplementedError:
            pass  # Windows: signal handlers via add_signal_handler aren't supported; Ctrl+C still raises KeyboardInterrupt
    await capture.run_forever()


def main() -> int:
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
