"""
drift/incois_client.py — SIH26143 Drift Subsystem

INCOIS Regional High-Resolution Hydrodynamic Layer:
Provides an interface to the Indian National Centre for Ocean Information Services (INCOIS)
High-resolution Ocean Operational Model (HOOM / ROMS) for the Arabian Sea and Indian EEZ
(1/48° ~ 2 km coastal resolution).

Designed with automatic fallback to Copernicus Marine GLORYS if INCOIS servers are
down, slow, or rate-limited.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests

logger = logging.getLogger("incois_client")

INCOIS_ERDDAP_BASE = "https://erddap.incois.gov.in/erddap/griddap"
INCOIS_DATASET_ID = "incois_hoom_arabian_sea_2km"  # INCOIS regional HOOM current product
REQUEST_TIMEOUT_SECONDS = 15


def fetch_incois_currents(
    bbox: List[float],
    start_dt: datetime,
    end_dt: datetime,
    out_dir: str = "data/cache/forcing",
) -> Optional[str]:
    """
    Attempts to fetch high-resolution (2 km) surface currents from INCOIS.
    bbox: [min_lon, min_lat, max_lon, max_lat]

    Returns local NetCDF path on success, or None on network/server timeout
    to trigger seamless fallback to Copernicus GLORYS.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(
        out_dir, f"incois_currents_{start_dt:%Y%m%d}_{end_dt:%Y%m%d}.nc"
    )

    if os.path.exists(out_path):
        logger.info("[incois] Already cached: %s", out_path)
        return out_path

    logger.info(
        "[incois] Requesting 2km HOOM currents from INCOIS for bbox=%s (%s -> %s)...",
        bbox, start_dt, end_dt,
    )

    # Formulate ERDDAP .nc query
    time_start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"{INCOIS_ERDDAP_BASE}/{INCOIS_DATASET_ID}.nc?"
        f"u[({time_start_str}):1:({time_end_str})][(0.0):1:(0.0)][({min_lat}):1:({max_lat})][({min_lon}):1:({max_lon})],"
        f"v[({time_start_str}):1:({time_end_str})][(0.0):1:(0.0)][({min_lat}):1:({max_lat})][({min_lon}):1:({max_lon})]"
    )

    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, stream=True)
        if resp.status_code == 200:
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            logger.info("[incois] Successfully saved 2km hydrodynamic grid -> %s", out_path)
            return out_path
        else:
            logger.warning(
                "[incois] INCOIS ERDDAP returned HTTP %d (%s). Falling back to Copernicus GLORYS.",
                resp.status_code, resp.text[:100] if resp.text else ""
            )
            return None
    except requests.RequestException as e:
        logger.info(
            "[incois] INCOIS server unreachable or timed out (%s). Falling back to Copernicus GLORYS.",
            e,
        )
        return None
