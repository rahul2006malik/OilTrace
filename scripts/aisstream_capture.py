#!/usr/bin/env python3
"""
SIH26143 / OilTrace — continuous AISstream.io live AIS capture.

Subscribes to a bounding box (default: Arabian Sea / Mumbai-Gulf corridor, matching
the GFW smoke-test region in the execution doc) and appends every message received
to a daily NDJSON file, so you accumulate a real, self-collected live-traffic cache
over the whole sprint. Reconnects automatically on any drop.

Setup:
    pip install websockets python-dotenv
    Put AISSTREAM_API_KEY=your_key_here in a .env file in the same folder as this
    script (this is loaded automatically below — no need to export it manually).

Run (keep it running for the whole sprint):
    python aisstream_capture.py
  or, safer against the whole process dying (not just the socket dropping):
    python run_ais_capture.py    (companion supervisor, restarts this script if it exits)

Output:
    data/raw/aisstream_capture/ais_YYYY-MM-DD.ndjson   (one JSON object per line)
    data/raw/aisstream_capture/capture.log             (connection/error log)

Stop:
    Ctrl+C
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from pathlib import Path

import websockets

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads .env in current working directory
    repo_root = Path(__file__).resolve().parent.parent
    load_dotenv(repo_root / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass  # falls back to real environment variables if python-dotenv isn't installed

API_KEY = os.environ.get("AISSTREAM_API_KEY")
if not API_KEY:
    raise SystemExit(
        "AISSTREAM_API_KEY is not set. Either:\n"
        "  1) pip install python-dotenv, and make sure .env (with AISSTREAM_API_KEY=...) "
        "is in the repository root or scripts folder, or\n"
        "  2) set it directly: export AISSTREAM_API_KEY='your_key_here' (Mac/Linux) "
        "or $env:AISSTREAM_API_KEY='your_key_here' (PowerShell)"
    )

# [[lat_min, lon_min], [lat_max, lon_max]] — Arabian Sea / Mumbai-Gulf corridor,
# same box used in the execution doc's GFW smoke test (Section 2). Widen this if
# your chosen demo corridor differs.
BOUNDING_BOXES = [[[15.0, 60.0], [22.0, 73.0]]]

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = str(REPO_ROOT / "data" / "raw" / "aisstream_capture")
LOG_FILE = os.path.join(OUTPUT_DIR, "capture.log")
WS_URL = "wss://stream.aisstream.io/v0/stream"

os.makedirs(OUTPUT_DIR, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def current_output_path() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return os.path.join(OUTPUT_DIR, f"ais_{day}.ndjson")


async def capture() -> None:
    subscribe_message = {
        "APIKey": API_KEY,
        "BoundingBoxes": BOUNDING_BOXES,
    }
    msg_count = 0
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(subscribe_message))
                logging.info("Connected and subscribed to bounding box %s", BOUNDING_BOXES)
                print("Connected. Capturing AIS traffic — Ctrl+C to stop.")

                async for raw_message in ws:
                    try:
                        message = json.loads(raw_message)
                    except json.JSONDecodeError:
                        logging.warning("Skipped a non-JSON message.")
                        continue

                    record = {
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                        "message": message,
                    }
                    with open(current_output_path(), "a") as f:
                        f.write(json.dumps(record) + "\n")

                    msg_count += 1
                    if msg_count == 1:
                        msg_type = message.get("MessageType", "Message")
                        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] Stream active ({msg_type}). Receiving vessel telemetry...", flush=True)
                    elif msg_count % 25 == 0:
                        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                        print(f"[{ts} UTC] Captured {msg_count} AIS messages so far...", flush=True)

                    if msg_count % 500 == 0:
                        logging.info("Captured %d messages so far.", msg_count)

        except (websockets.ConnectionClosed, OSError) as e:
            logging.warning("Connection dropped (%s). Reconnecting in 10s.", e)
            print(f"Connection dropped ({e}). Reconnecting in 10s...")
            await asyncio.sleep(10)
        except Exception as e:  # noqa: BLE001 — keep the capture loop alive no matter what
            logging.error("Unexpected error (%s). Reconnecting in 15s.", e)
            await asyncio.sleep(15)


if __name__ == "__main__":
    try:
        asyncio.run(capture())
    except KeyboardInterrupt:
        print("\nStopped. Everything captured so far is already saved to disk — nothing lost.")