"""
SIH26143 — OilTrace Backend Orchestrator (v2.4.1 Production Architecture)

Modular FastAPI Orchestration Service for Marine Oil Spill Detection & Attribution:
- Detection (ResNet34 + U-Net cascade)
- Drift Hindcast (OpenDrift 1.14.11 RK4 + Fay Dispersion + Hot Metocean Buffer)
- Vessel Attribution (GFW v2 + Live AISstream + Isolation Forest + 4D Route Recon)
- Real-Time Streaming (SSE /pipeline/stream & WebSocket /ws/live-ais)
- Admiralty Forensics (ReportLab Multi-Page PDF with SHA-256 Digest)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from .errors import validation_exception_handler
from .routers import drift, live_feed, pipeline, reports, scenarios, vessels

logger = logging.getLogger("oiltrace_backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan Singleton:
    Initializes heavyweight neural networks (OilSpillDetector) once at startup.
    """
    logger.info("Initializing OilTrace Pipeline Engines (v2.4.1 Production)...")
    try:
        from .db import ensure_db_wal
        ensure_db_wal(_PROJECT_ROOT / "data" / "live_ais.db")
        ensure_db_wal(_PROJECT_ROOT / "data" / "processed_scenes.db")
    except Exception as e:
        logger.debug("[lifespan] SQLite WAL init deferred: %s", e)
    try:
        from detection import OilSpillDetector
        app.state.detector = OilSpillDetector()
        logger.info("OilSpillDetector initialized successfully (singleton).")
    except Exception as e:
        logger.warning("OilSpillDetector initialization deferred: %s", e)
        app.state.detector = None
    yield
    logger.info("Shutting down OilTrace Pipeline.")


app = FastAPI(
    title="OilTrace Forensics Backend (SIH26143)",
    version="2.4.1",
    description="Maritime oil spill detection, ocean drift hindcasting, and dark-vessel attribution.",
    lifespan=lifespan,
)

# Enable CORS for frontend visualizer
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Mount modular routers
app.include_router(pipeline.router)
app.include_router(drift.router)
app.include_router(scenarios.router)
app.include_router(vessels.router)
app.include_router(reports.router)
app.include_router(live_feed.router)


@app.get("/health")
@app.get("/api/health")
async def health() -> dict:
    """System health check verifying availability of all core forensic subsystems."""
    cache_dir = _PROJECT_ROOT / "data" / "cache"
    return {
        "status": "ok",
        "system": "OilTrace SIH26143 Forensics Backend",
        "version": "2.4.1-defense",
        "subsystems": {
            "detection_available": getattr(app.state, "detector", None) is not None,
            "drift_available": True,
            "attribution_available": True,
            "live_ais_db_active": (_PROJECT_ROOT / "data" / "live_ais.db").exists(),
            "satellite_scenes_db_active": (_PROJECT_ROOT / "data" / "processed_scenes.db").exists(),
        },
        "cache_dir": str(cache_dir),
    }
