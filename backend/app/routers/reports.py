"""
backend/app/routers/reports.py — SIH26143

Reports Router:
Generates and serves official, publication-quality multi-page Admiralty Forensics PDF reports
with cryptographic SHA-256 evidence digests and UNCLOS enforcement directives.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from ..reports.pdf_generator import generate_admiralty_pdf_report

logger = logging.getLogger("reports_router")
router = APIRouter(tags=["reports"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPORTS_DIR = _PROJECT_ROOT / "data" / "cache" / "reports"


def _get_project_cache_dir() -> Path:
    curr = Path(__file__).resolve().parent.parent.parent
    for parent in [curr, curr.parent]:
        candidate = parent / "data" / "cache"
        if candidate.exists():
            return candidate
    return Path("data/cache")


@router.post("/api/reports/generate")
async def generate_report(payload: dict, request: Request):
    """
    Renders an official multi-page Admiralty Forensics PDF report for the incident
    and returns metadata with downloadable URL, or direct FileResponse if requested.
    """
    spill_id = payload.get("scenarioId") or payload.get("spill_id") or "SPILL-2026-ARABIAN-001"
    cache_dir = _get_project_cache_dir()

    # Scenario-specific resolution
    scen_attr_file = None
    scen_slick_file = None
    for sub in [spill_id, f"scenario_{spill_id.lower().replace('-', '_')}"]:
        candidate_dir = cache_dir / "scenarios" / sub
        if candidate_dir.exists():
            scen_attr_file = candidate_dir / "attribution_result.json"
            scen_slick_file = candidate_dir / "slick_detection.geojson"
            break

    attr_file = scen_attr_file if (scen_attr_file and scen_attr_file.exists()) else (cache_dir / "attribution_result.json")
    slick_file = scen_slick_file if (scen_slick_file and scen_slick_file.exists()) else (cache_dir / "flagship_slick_detection.geojson")

    attr_data = {}
    slick_data = {}

    if attr_file.exists():
        try:
            attr_data = json.loads(attr_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if slick_file.exists():
        try:
            slick_data = json.loads(slick_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # If payload provided custom lead vessel data, ensure it's represented
    if payload.get("lead_mmsi") and not attr_data.get("candidates"):
        attr_data["candidates"] = [{
            "vessel_id": payload["lead_mmsi"],
            "vessel_name": payload.get("lead_vessel_name", "UNKNOWN"),
            "suspicion_score": payload.get("suspicion_score", 0.85),
            "flag_country": payload.get("flag_state", "LBR"),
            "data_provenance": "real_gfw",
        }]

    scenario_context = {
        "spill_id": spill_id,
        "slick": slick_data,
    }

    # Generate the actual multi-page PDF on disk via threadpool
    pdf_path = await run_in_threadpool(
        generate_admiralty_pdf_report,
        spill_id=spill_id,
        scenario_data=scenario_context,
        attribution_data=attr_data,
        out_dir=REPORTS_DIR,
    )

    pdf_filename = Path(pdf_path).name

    # Check if client explicitly asked for raw PDF binary
    accept = request.headers.get("accept", "")
    if payload.get("raw") is True or "application/pdf" in accept:
        return FileResponse(
            path=str(pdf_path),
            filename=f"NTRO_Admiralty_Report_{spill_id}.pdf",
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="NTRO_Admiralty_Report_{spill_id}.pdf"',
                "X-Report-Id": f"RPT-{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}-{spill_id}",
                "X-Generated-At": datetime.now(tz=timezone.utc).isoformat(),
                "X-File-Size": str(os.path.getsize(pdf_path)),
            },
        )

    return {
        "reportId": f"RPT-{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}-{spill_id}",
        "scenarioId": spill_id,
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
        "pdfUrl": f"/reports/{pdf_filename}",
        "status": "READY",
        "fileSizeBytes": os.path.getsize(pdf_path),
    }


@router.get("/api/reports/metadata/{spill_id}")
async def get_report_metadata(spill_id: str) -> dict:
    """Returns report metadata JSON (report ID, URL, size) without generating or streaming the PDF."""
    return {
        "reportId": f"RPT-{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}-{spill_id}",
        "scenarioId": spill_id,
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
        "pdfUrl": f"/reports/{spill_id}_report.pdf",
        "status": "READY",
    }


@router.get("/reports/{filename}")
async def serve_report_pdf(filename: str):
    """Serves a previously generated PDF file by filename."""
    file_path = REPORTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Report PDF not found")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/pdf"
    )
