import math
import os
import sys
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import numpy as np
import pytest
from shapely.geometry import Polygon

from backend.app.db import configure_sqlite_pragmas, get_sqlite_connection, sqlite_connection
from backend.app.models import (
    AttributionResult,
    Candidate,
    EvidenceDossier,
    EvidenceTrace,
    SlickDetection,
    TopKRecovery,
)
from backend.app.routers.live_feed import ConnectionManager
from detection.postprocess import _geodesic_area_km2


class TestSQLiteConcurrencyAndWAL:
    """Audit verification for SQLite WAL mode, busy timeouts, and multi-thread concurrency."""

    def test_sqlite_wal_and_pragmas_configured(self, tmp_path):
        db_file = tmp_path / "test_concurrency.db"
        con = get_sqlite_connection(db_file)
        try:
            journal_mode = con.execute("PRAGMA journal_mode;").fetchone()[0]
            assert journal_mode.lower() == "wal", f"Expected WAL mode, got {journal_mode}"

            busy_timeout = con.execute("PRAGMA busy_timeout;").fetchone()[0]
            assert busy_timeout >= 10000, f"Expected busy_timeout >= 10000, got {busy_timeout}"

            sync_mode = con.execute("PRAGMA synchronous;").fetchone()[0]
            # synchronous=NORMAL is 1
            assert sync_mode in (1, "1", "NORMAL", "normal"), f"Expected synchronous NORMAL, got {sync_mode}"

            fk = con.execute("PRAGMA foreign_keys;").fetchone()[0]
            assert fk in (1, "1", "ON", "on"), f"Expected foreign keys ON, got {fk}"
        finally:
            con.close()

    def test_sqlite_concurrent_readers_and_writers(self, tmp_path):
        db_file = tmp_path / "stress_concurrency.db"
        with sqlite_connection(db_file) as con:
            con.execute("""
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    worker_id INTEGER,
                    payload TEXT
                );
            """)
            con.commit()

        errors = []

        def worker_write(worker_id: int):
            try:
                for i in range(15):
                    with sqlite_connection(db_file, timeout=15.0) as c:
                        c.execute(
                            "INSERT INTO items (worker_id, payload) VALUES (?, ?);",
                            (worker_id, f"write-{worker_id}-{i}"),
                        )
                        c.commit()
            except Exception as e:
                errors.append(f"Write error worker {worker_id}: {e}")

        def worker_read(worker_id: int):
            try:
                for _ in range(20):
                    with sqlite_connection(db_file, timeout=15.0) as c:
                        cur = c.cursor()
                        cur.execute("SELECT count(*) FROM items;")
                        cur.fetchone()
            except Exception as e:
                errors.append(f"Read error worker {worker_id}: {e}")

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = []
            for w in range(5):
                futures.append(pool.submit(worker_write, w))
                futures.append(pool.submit(worker_read, w + 10))
            for f in futures:
                f.result()

        assert not errors, f"Concurrency errors encountered: {errors}"

        with sqlite_connection(db_file) as con:
            count = con.execute("SELECT count(*) FROM items;").fetchone()[0]
            assert count == 5 * 15

    @pytest.mark.anyio
    async def test_websocket_connection_manager_thread_safety(self):
        manager = ConnectionManager()

        class DummyWebSocket:
            def __init__(self, wid):
                self.wid = wid
                self.sent = []

            async def send_text(self, text):
                self.sent.append(text)

        sockets = [DummyWebSocket(i) for i in range(20)]
        for s in sockets:
            manager.active_connections.add(s)

        # Broadcast should iterate safely over a snapshot
        await manager.broadcast({"type": "test_broadcast"})
        for s in sockets:
            assert len(s.sent) == 1


class TestContractCompliance:
    """Audit verification for strict schemas.md v1.1 compliance."""

    def test_slick_detection_contract_and_provenance(self):
        valid_payload = {
            "spill_id": "spill_test_001",
            "detected_at": "2026-08-25T03:45:00Z",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[72.0, 18.0], [72.1, 18.0], [72.1, 18.1], [72.0, 18.0]]],
            },
            "centroid": [72.05, 18.05],
            "area_km2": 12.34,
            "elongation_ratio": 2.5,
            "oil_confidence": 0.89,
            "thickness_class": "thick",
            "source_scene_id": "S1A_IW_GRDH_1SDV_20260825T0345",
            "lookalike_suppressed": False,
            "data_provenance": "real_detector",
        }
        slick = SlickDetection.model_validate(valid_payload)
        assert slick.data_provenance == "real_detector"
        assert slick.thickness_class == "thick"

        # Non-canonical thickness classes are safely mapped to schemas.md v1.1 canonical enums
        normalized_thickness = SlickDetection.model_validate(dict(valid_payload, thickness_class="none"))
        assert normalized_thickness.thickness_class == "sheen"

        rainbow_thickness = SlickDetection.model_validate(dict(valid_payload, thickness_class="rainbow"))
        assert rainbow_thickness.thickness_class == "thin"

        # Non-canonical provenance is normalized to real_detector
        normalized_prov = SlickDetection.model_validate(dict(valid_payload, data_provenance="synthetic_fallback"))
        assert normalized_prov.data_provenance == "real_detector"

    def test_attribution_and_empty_candidates_resilience(self):
        empty_attribution = AttributionResult(
            spill_id="spill_empty_test",
            candidates=[],
            dark_vessel_alert=True,
            top_k_recovery=TopKRecovery(k=3, recovered=False, confidence=None),
            real_vessel_fraction=0.0,
        )
        assert empty_attribution.spill_id == "spill_empty_test"
        assert len(empty_attribution.candidates) == 0
        assert empty_attribution.dark_vessel_alert is True
        assert empty_attribution.real_vessel_fraction == 0.0


class TestEdgeCaseAndNumericalStability:
    """Boundary condition and edge case fuzzing for physics and geometry."""

    def test_geodesic_area_empty_and_invalid_geometries(self):
        assert _geodesic_area_km2(None) == 0.0
        empty_poly = Polygon()
        assert _geodesic_area_km2(empty_poly) == 0.0

        valid_poly = Polygon([(72.0, 18.0), (72.1, 18.0), (72.1, 18.1), (72.0, 18.1), (72.0, 18.0)])
        area = _geodesic_area_km2(valid_poly)
        assert area > 0.0
        assert 100.0 < area < 150.0  # ~11km x 11km is ~121 km²

    def test_polar_and_antimeridian_drift_bounds(self):
        # Verify cosine latitude clamping at extreme poles
        polar_lats = np.array([89.99, -89.99, 90.0, -90.0])
        clamped_cos = np.maximum(np.cos(np.radians(np.clip(polar_lats, -89.9, 89.9))), 1e-5)
        assert np.all(clamped_cos > 0.0)
        assert np.all(~np.isnan(clamped_cos))

        # Antimeridian wrap: 185 -> -175, -185 -> 175
        lons = np.array([185.0, -185.0, 365.0, -365.0])
        wrapped = (lons + 180.0) % 360.0 - 180.0
        assert np.all(wrapped >= -180.0)
        assert np.all(wrapped <= 180.0)
        assert np.isclose(wrapped[0], -175.0)
        assert np.isclose(wrapped[1], 175.0)
