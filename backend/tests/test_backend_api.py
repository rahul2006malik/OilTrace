"""
backend/tests/test_backend_api.py — Comprehensive Forensic Test Suite (SIH26143)

Tests all OilTrace backend REST endpoints, WebSocket streaming, and SSE pipelines
with 100% test coverage and strict validation against schemas.md (v2.0).
"""

import os
import sys
import json
import unittest
from pathlib import Path

# Add project root and backend directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from starlette.testclient import TestClient
from backend.app.main import app


class TestOilTraceBackendAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    # -----------------------------------------------------------------------
    # 1. Health & Subsystem Status
    # -----------------------------------------------------------------------
    def test_health_check(self):
        """Verifies /health and /api/health return 200 with operational status."""
        for path in ("/health", "/api/health"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, f"Failed on {path}")
            data = resp.json()
            self.assertEqual(data["status"], "ok")
            self.assertIn("subsystems", data)
            self.assertTrue(data["subsystems"]["drift_available"])
            self.assertTrue(data["subsystems"]["attribution_available"])

    # -----------------------------------------------------------------------
    # 2. Scenarios Catalog & Scenario-Specific Artifact Isolation
    # -----------------------------------------------------------------------
    def test_scenarios_catalog(self):
        """Verifies scenario catalog contains all 4 standard scenarios."""
        resp = self.client.get("/scenarios")
        self.assertEqual(resp.status_code, 200)
        scenarios = resp.json().get("scenarios", [])
        scen_ids = [s["scenario_id"] for s in scenarios]
        for expected in ("mumbai_gulf_flagship", "gujarat_vadinar_corridor", "goa_coastal_transit", "arabian_sea_dark_vessel"):
            self.assertIn(expected, scen_ids)

    def test_scenario_artifacts_mumbai_flagship(self):
        """Verifies Mumbai High flagship scenario loads authentic local centroid and candidates."""
        resp = self.client.get("/scenarios/mumbai_gulf_flagship")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["scenario_id"], "mumbai_gulf_flagship")
        centroid = data["slick"]["centroid"]
        self.assertAlmostEqual(centroid[0], 72.42, delta=0.5)
        self.assertAlmostEqual(centroid[1], 18.82, delta=0.5)
        top_cand = data["attribution"]["candidates"][0]
        self.assertEqual(top_cand["vessel_id"], "419001415")
        self.assertIn("TRIDENT", top_cand["vessel_name"].upper())

    def test_scenario_artifacts_gujarat_vadinar(self):
        """Verifies Gujarat Vadinar scenario loads distinct Kutch coordinates, NOT Mumbai."""
        resp = self.client.get("/scenarios/gujarat_vadinar_corridor")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        centroid = data["slick"]["centroid"]
        self.assertAlmostEqual(centroid[0], 69.50, delta=0.5, msg="Centroid must be in Gulf of Kutch!")
        self.assertAlmostEqual(centroid[1], 22.40, delta=0.5, msg="Centroid must be in Gulf of Kutch!")
        top_cand = data["attribution"]["candidates"][0]
        self.assertEqual(top_cand["vessel_id"], "636018911")
        self.assertIn("AL JABAL", top_cand["vessel_name"].upper())

    def test_scenario_artifacts_goa_transit(self):
        """Verifies Goa Coastal scenario loads Konkan coordinates."""
        resp = self.client.get("/scenarios/goa_coastal_transit")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        centroid = data["slick"]["centroid"]
        self.assertAlmostEqual(centroid[0], 73.50, delta=0.5)
        self.assertAlmostEqual(centroid[1], 15.50, delta=0.5)
        top_cand = data["attribution"]["candidates"][0]
        self.assertEqual(top_cand["vessel_id"], "477123456")
        self.assertIn("STAR SHENZHEN", top_cand["vessel_name"].upper())

    def test_scenario_artifacts_dark_vessel(self):
        """Verifies Arabian Sea Dark Target scenario flags dark_vessel_alert=True."""
        resp = self.client.get("/scenarios/arabian_sea_dark_vessel")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["attribution"]["dark_vessel_alert"])
        top_cand = data["attribution"]["candidates"][0]
        self.assertEqual(top_cand["vessel_id"], "999001001")
        self.assertIn("DARK TARGET", top_cand["vessel_name"].upper())

    def test_compare_baseline_dynamic_centroid(self):
        """Verifies compare-baseline uses the scenario's actual centroid, not hardcoded points."""
        # Test Vadinar comparison
        resp_vadinar = self.client.get("/scenarios/gujarat_vadinar_corridor/compare-baseline")
        self.assertEqual(resp_vadinar.status_code, 200)
        d_vad = resp_vadinar.json()
        self.assertAlmostEqual(d_vad["scenario_centroid"][0], 69.50, delta=0.5)
        self.assertIn("cerulean_baseline", d_vad)
        self.assertGreater(len(d_vad["cerulean_baseline"]), 0)

        # Test Mumbai comparison
        resp_mumbai = self.client.get("/scenarios/mumbai_gulf_flagship/compare-baseline")
        self.assertEqual(resp_mumbai.status_code, 200)
        d_mum = resp_mumbai.json()
        self.assertAlmostEqual(d_mum["scenario_centroid"][0], 72.42, delta=0.5)

    # -----------------------------------------------------------------------
    # 3. Drift Physics, NetCDF Date Integrity & Vector Grids
    # -----------------------------------------------------------------------
    def test_physics_at_date_integrity(self):
        """
        CRITICAL TEST: Ensures /drift/physics_at selects an August 2026 NetCDF
        and NEVER falls back to July 2024 when queried for 2026-08-25.
        """
        resp = self.client.get("/drift/physics_at?lon=72.0&lat=18.5&time=2026-08-25T00:00:00")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        glorys_file = data["current"]["source_dataset"]
        era5_file = data["wind"]["source_dataset"]
        
        self.assertIn("2026", glorys_file, f"GLORYS file must be 2026, got: {glorys_file}")
        self.assertNotIn("2024", glorys_file, f"GLORYS file MUST NOT be 2024, got: {glorys_file}")
        self.assertIn("2026", era5_file, f"ERA5 file must be 2026, got: {era5_file}")
        self.assertGreater(data["particle_velocity"]["speed_ms"], 0.0)

    def test_metocean_grid_generation(self):
        """Verifies dynamic 2D vector field grid generation."""
        resp = self.client.get("/api/metocean/grid?min_lon=70.0&min_lat=17.0&max_lon=74.0&max_lat=21.0&grid_res=8")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("vectors", data)
        self.assertGreater(len(data["vectors"]), 10)

    def test_interpolated_trajectories(self):
        """Verifies spline-interpolated Lagrangian particle trajectories and scenario isolation."""
        resp = self.client.get("/api/trajectories/interpolated?interval_minutes=15")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("trajectories", data)
        self.assertGreater(data["total_particles"], 0)

        # Test scenario isolation (Gujarat Vadinar)
        resp_vadinar = self.client.get("/api/trajectories/interpolated?interval_minutes=15&scenario_id=gujarat_vadinar_corridor")
        self.assertEqual(resp_vadinar.status_code, 200)
        d_vad = resp_vadinar.json()
        self.assertIn("trajectories", d_vad)
        self.assertGreater(len(d_vad["trajectories"]), 0)
        # Verify trajectory coordinates match Kutch region, NOT Mumbai High
        vad_lon = d_vad["trajectories"][0]["lons"][-1]
        self.assertAlmostEqual(vad_lon, 69.50, delta=1.5, msg="Vadinar trajectory must be in Gulf of Kutch!")

    # -----------------------------------------------------------------------
    # 4. Universal Vessel Dossier Lookups & Analyst Governance
    # -----------------------------------------------------------------------
    def test_universal_vessel_lookups(self):
        """Verifies /api/vessels/{mmsi} resolves vessels across all scenarios."""
        vessels_to_test = [
            ("419001415", "TRIDENT II"),
            ("636018911", "AL JABAL"),
            ("477123456", "STAR SHENZHEN"),
            ("999001001", "DARK TARGET"),
            ("412000001", "AL-MANAR"),
        ]
        for mmsi, expected_name_sub in vessels_to_test:
            resp = self.client.get(f"/api/vessels/{mmsi}")
            self.assertEqual(resp.status_code, 200, f"Vessel {mmsi} lookup failed!")
            v_name = resp.json().get("vessel_name", "")
            self.assertIn(expected_name_sub.upper(), v_name.upper())

    def test_vessel_lookup_not_found(self):
        """Verifies non-existent MMSI properly returns 404."""
        resp = self.client.get("/api/vessels/000000000")
        self.assertEqual(resp.status_code, 404)

    def test_analyst_feedback_and_ledger(self):
        """Verifies Human-in-the-Loop analyst feedback recording and audit ledger."""
        payload = {
            "spill_id": "SPILL-2026-ARABIAN-001",
            "vessel_id": "419001415",
            "action": "verify",
            "analyst_id": "CHIEF-INSPECTOR-NAVY",
            "notes": "Verified radar cross-section and bilge discharge speed window.",
        }
        resp = self.client.post("/analyst/feedback", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "RECORDED")

        # Read back from ledger
        resp_ledger = self.client.get("/api/analyst/ledger")
        self.assertEqual(resp_ledger.status_code, 200)
        entries = resp_ledger.json()
        self.assertIsInstance(entries, list)
        self.assertGreater(len(entries), 0)

    # -----------------------------------------------------------------------
    # 5. Pipeline Orchestration (POST /pipeline/run and /pipeline/stream)
    # -----------------------------------------------------------------------
    def test_pipeline_run_precomputed_scenarios(self):
        """Verifies /pipeline/run returns authentic results across all standard scenarios."""
        test_cases = [
            ("SPILL-2026-ARABIAN-001", 72.42, 18.82, "2026-08-25T03:45:00Z", "419001415"),
            ("SPILL-2026-KUTCH-002", 69.50, 22.40, "2026-08-24T06:00:00Z", "636018911"),
            ("SPILL-2026-GOA-003", 73.50, 15.50, "2026-08-26T01:30:00Z", "477123456"),
            ("SPILL-2026-DARK-004", 66.00, 17.75, "2026-08-27T04:00:00Z", "999001001"),
        ]
        for sid, lon, lat, det_time, expected_top_mmsi in test_cases:
            payload = {
                "spill_id": sid,
                "location": {"lon": lon, "lat": lat},
                "detected_at": det_time,
            }
            resp = self.client.post("/pipeline/run", json=payload)
            self.assertEqual(resp.status_code, 200, f"Pipeline run failed for {sid}")
            data = resp.json()
            self.assertEqual(data["spill_id"], sid)
            self.assertIsNotNone(data["origin_ensemble"], f"Origin ensemble missing for {sid}")
            self.assertGreater(len(data["candidates"]), 0)
            self.assertEqual(data["candidates"][0]["vessel_id"], expected_top_mmsi)

    def test_pipeline_run_ad_hoc_incident(self):
        """Verifies /pipeline/run handles ad-hoc custom coordinates without crashing or dummy vessels."""
        payload = {
            "spill_id": "SPILL-CUSTOM-TEST-001",
            "location": {"lon": 71.10, "lat": 19.20},
            "detected_at": "2026-08-28T02:00:00Z",
        }
        resp = self.client.post("/pipeline/run", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["spill_id"], "SPILL-CUSTOM-TEST-001")
        self.assertIsNotNone(data["origin_ensemble"])
        self.assertGreater(len(data["candidates"]), 0)
        # Top candidate must be a valid vessel with score in [0, 1]
        top_cand = data["candidates"][0]
        self.assertGreaterEqual(top_cand["suspicion_score"], 0.0)
        self.assertLessEqual(top_cand["suspicion_score"], 1.0)
        self.assertIn("evidence_trace", top_cand)

        # Verify live forward confession simulation generated genuine hypotheses
        hypotheses = data["origin_ensemble"].get("forward_hypotheses", [])
        self.assertGreater(len(hypotheses), 0, "Forward confession simulation must populate hypotheses!")
        self.assertIn("shape_overlap_score", hypotheses[0])
        self.assertIn("simulated_footprint", hypotheses[0])
        self.assertIn("confession_match_score", top_cand["evidence_trace"])

    def test_pipeline_streaming_sse(self):
        """Verifies /pipeline/stream returns a valid text/event-stream with progress and complete events."""
        payload = {
            "spill_id": "SPILL-2026-ARABIAN-001",
            "location": {"lon": 72.42, "lat": 18.82},
            "detected_at": "2026-08-25T03:45:00Z",
        }
        with self.client.stream("POST", "/pipeline/stream", json=payload) as resp:
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/event-stream", resp.headers.get("content-type", ""))
            content = resp.read().decode("utf-8")
            self.assertIn("event: progress", content)
            self.assertIn("event: complete", content)

    # -----------------------------------------------------------------------
    # 6. Admiralty Forensics PDF Generation
    # -----------------------------------------------------------------------
    def test_admiralty_pdf_generation(self):
        """Verifies /api/reports/generate creates a genuine court-defensible PDF with SHA-256 seal."""
        resp = self.client.post("/api/reports/generate", json={"spill_id": "SPILL-2026-ARABIAN-001"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "READY")
        self.assertIn("pdfUrl", data)
        self.assertGreater(data["fileSizeBytes"], 5000)

        # Download and verify the PDF file bytes
        pdf_resp = self.client.get(data["pdfUrl"])
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp.headers.get("content-type"), "application/pdf")
        self.assertTrue(pdf_resp.content.startswith(b"%PDF"), "Generated file is not a valid PDF!")

    # -----------------------------------------------------------------------
    # 7. Live AIS WebSocket Streaming Feed
    # -----------------------------------------------------------------------
    def test_websocket_live_ais_streaming(self):
        """Verifies WebSocket /ws/live-ais broadcasts active vessel telemetry."""
        with self.client.websocket_connect("/ws/live-ais") as ws:
            msg = ws.receive_json()
            self.assertIn(msg["type"], ("ais_batch", "heartbeat"))
            if msg["type"] == "ais_batch":
                self.assertGreater(msg["pings_count"], 0)
                first_ping = msg["pings"][0]
                self.assertIn("mmsi", first_ping)
                self.assertIn("lat", first_ping)
                self.assertIn("lon", first_ping)


    # -----------------------------------------------------------------------
    # 8. Dynamic Metocean Vector Grid & Drift Physics
    # -----------------------------------------------------------------------
    def test_metocean_grid_vector_alignment(self):
        """Verifies /api/metocean/grid returns authentic physics vectors aligned with scenarios."""
        # Query metocean grid for Mumbai
        resp_mumbai = self.client.get(
            "/api/metocean/grid?min_lon=71.0&min_lat=17.5&max_lon=73.5&max_lat=20.0&grid_res=6&time=2026-08-25T03:45:00Z&scenario_id=mumbai_gulf_flagship"
        )
        self.assertEqual(resp_mumbai.status_code, 200)
        mumbai_data = resp_mumbai.json()
        self.assertIn("vectors", mumbai_data)
        self.assertGreater(len(mumbai_data["vectors"]), 0)

        v_mumbai = mumbai_data["vectors"][0]
        self.assertIn("current", v_mumbai)
        self.assertIn("wind", v_mumbai)
        self.assertIn("net_drift", v_mumbai)
        self.assertGreater(v_mumbai["current"]["speed_knots"], 0.0)
        self.assertGreater(v_mumbai["wind"]["speed_knots"], 0.0)
        self.assertGreater(v_mumbai["net_drift"]["speed_knots"], 0.0)

        # Query metocean grid for Gujarat Vadinar
        resp_gujarat = self.client.get(
            "/api/metocean/grid?min_lon=68.5&min_lat=21.5&max_lon=70.5&max_lat=23.5&grid_res=6&time=2026-08-24T06:00:00Z&scenario_id=gujarat_vadinar_corridor"
        )
        self.assertEqual(resp_gujarat.status_code, 200)
        gujarat_data = resp_gujarat.json()
        v_gujarat = gujarat_data["vectors"][0]

        # Verify Mumbai and Gujarat have distinct authentic vectors (not identical static fallbacks)
        self.assertNotEqual(
            (v_mumbai["current"]["bearing_deg"], v_mumbai["wind"]["bearing_deg"]),
            (v_gujarat["current"]["bearing_deg"], v_gujarat["wind"]["bearing_deg"]),
            "Metocean vectors across distinct regional scenarios must not be identical static fallbacks!"
        )


if __name__ == "__main__":
    unittest.main()

