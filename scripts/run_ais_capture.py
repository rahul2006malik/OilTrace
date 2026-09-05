#!/usr/bin/env python3
"""
SIH26143 / OilTrace — pure-Python supervisor for aisstream_capture.py.

Restarts the capture script if the whole process ever dies outright (not just a
socket drop — that's already handled inside aisstream_capture.py itself). No bash
required; works the same way on Windows, Mac, and Linux.

Setup (same as aisstream_capture.py):
    pip install websockets
    Windows PowerShell:  $env:AISSTREAM_API_KEY="your_key_here"
    Windows cmd.exe:      set AISSTREAM_API_KEY=your_key_here
    Mac/Linux:            export AISSTREAM_API_KEY="your_key_here"

Run (leave this running in its own terminal window / tab for the whole sprint):
    python run_ais_capture.py

Stop:
    Ctrl+C in that terminal window.
"""

import datetime
import subprocess
import sys
import time
from pathlib import Path


def log(msg: str) -> None:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(f"[{ts}] {msg}")


def main() -> None:
    script_path = Path(__file__).resolve().parent / "aisstream_capture.py"
    while True:
        log("Starting aisstream_capture.py")
        try:
            proc = subprocess.run([sys.executable, str(script_path)])
            log(f"aisstream_capture.py exited with code {proc.returncode} — restarting in 10s")
        except KeyboardInterrupt:
            log("Stopped by user (Ctrl+C).")
            break
        except Exception as e:  # noqa: BLE001 — supervisor must never itself crash silently
            log(f"Supervisor error: {e} — restarting in 10s")
        time.sleep(10)


if __name__ == "__main__":
    main()
