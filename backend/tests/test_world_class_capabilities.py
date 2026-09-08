import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / 'backend'))

import numpy as np
import pytest

from attribution.route_reconstruction import (
    reconstruct_and_score_vessel,
    ReconstructedTrack,
)
from drift.buffer_manager import analytical_monsoon_forcing
from drift.backward_ensemble import fast_rk4_backward_ensemble
from backend.app.models import Candidate, EvidenceTrace, RouteReconstruction


class TestAnalyticalMonsoonAndEkmanDrift:
    """Verification for Analytical Seasonal Monsoon and Ekman Boundary Drift."""

    def test_summer_southwest_monsoon_dynamics(self):
        """In July (Summer Monsoon), winds blow SW -> NE, surface drift deflected right."""
        target_dt = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        lons = np.array([85.0])
        lats = np.array([15.0])

        u_curr, v_curr, u_wind, v_wind = analytical_monsoon_forcing(lons, lats, target_dt)

        assert u_wind[0] > 0.0, f"Expected eastward summer wind, got {u_wind[0]}"
        assert v_wind[0] > 0.0, f"Expected northward summer wind, got {v_wind[0]}"

        wind_speed = math.hypot(u_wind[0], v_wind[0])
        assert 4.0 <= wind_speed <= 16.0, f"Expected realistic wind speed, got {wind_speed}"

        curr_speed = math.hypot(u_curr[0], v_curr[0])
        assert 0.05 <= curr_speed <= 1.5, f"Expected realistic surface current speed, got {curr_speed}"

    def test_winter_northeast_monsoon_dynamics(self):
        """In January (Winter Monsoon), winds blow NE -> SW."""
        target_dt = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        lons = np.array([68.0])
        lats = np.array([18.0])

        u_curr, v_curr, u_wind, v_wind = analytical_monsoon_forcing(lons, lats, target_dt)

        assert u_wind[0] < 0.0, f"Expected westward winter wind, got {u_wind[0]}"
        assert v_wind[0] < 0.0, f"Expected southward winter wind, got {v_wind[0]}"

    def test_rk4_backward_ensemble_with_analytical_blend(self):
        """Fast RK4 backward ensemble seamlessly blends analytical forcing when out of bounds."""
        curr_file = str(PROJECT_ROOT / "data" / "cache" / "forcing" / "glorys_currents_20260826_20260828.nc")
        wind_file = str(PROJECT_ROOT / "data" / "cache" / "forcing" / "era5_wind_20260826_20260828.nc")
        if not (Path(curr_file).exists() and Path(wind_file).exists()):
            pytest.skip("Forcing files not present")

        # Coordinates slightly outside or near the boundary of the dataset
        origin_lon = 72.85
        origin_lat = 19.00
        detected_at = datetime(2026, 8, 27, 4, 0)
        hours_back = 6
        n_particles = 10

        endpoints_lon, endpoints_lat, endpoints_time, trajectories, diagnostics = fast_rk4_backward_ensemble(
            lon=origin_lon,
            lat=origin_lat,
            detection_time=detected_at,
            currents_path=curr_file,
            winds_path=wind_file,
            n_members=n_particles,
            backward_hours=hours_back,
            time_step_s=1800,
        )

        assert len(endpoints_lon) == n_particles
        assert not np.isnan(endpoints_lon).any(), "Lon cannot have NaNs"
        assert not np.isnan(endpoints_lat).any(), "Lat cannot have NaNs"
        assert len(trajectories) == n_particles
        assert (endpoints_lon >= 65.0).all() and (endpoints_lon <= 80.0).all()
        assert (endpoints_lat >= 15.0).all() and (endpoints_lat <= 25.0).all()


class Test4DSpatiotemporalRayTracing:
    """Verification for 4D CPA Closest Point of Approach and Causal Veto Engine."""

    def _build_dummy_cone(self, origin_lon=72.80, origin_lat=18.90):
        d = 0.05
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"probability": 0.50},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [origin_lon - d, origin_lat - d],
                            [origin_lon + d, origin_lat - d],
                            [origin_lon + d, origin_lat + d],
                            [origin_lon - d, origin_lat + d],
                            [origin_lon - d, origin_lat - d],
                        ]],
                    },
                },
            ],
        }

    def test_spatiotemporal_cpa_causal_veto(self):
        """A vessel crossing origin 8 hours after release is causally vetoed."""
        spill_time = datetime(2026, 8, 27, 0, 0)
        pings = [
            {"lon": 72.70, "lat": 18.80, "timestamp": (spill_time + timedelta(hours=7)).isoformat(), "sog": 14.0, "cog": 45.0},
            {"lon": 72.80, "lat": 18.90, "timestamp": (spill_time + timedelta(hours=8)).isoformat(), "sog": 14.0, "cog": 45.0},
            {"lon": 72.90, "lat": 19.00, "timestamp": (spill_time + timedelta(hours=9)).isoformat(), "sog": 14.0, "cog": 45.0},
        ]
        cone = self._build_dummy_cone()

        recon = reconstruct_and_score_vessel(
            vessel_id="999000111",
            ais_fixes=pings,
            origin_cone_fc=cone,
            spill_time=spill_time,
        )

        assert recon.cpa_distance_km < 3.0, "Spatially near origin"
        assert recon.cpa_time_diff_hours >= 7.0, "Temporally far from spill release"
        assert recon.causal_veto is True, "Must trigger causal veto"
        assert recon.ray_trace_score < 0.25, f"Score must be severely penalized, got {recon.ray_trace_score}"

    def test_spatiotemporal_cpa_acceptance(self):
        """A vessel crossing origin within 30 minutes of release is accepted with high score."""
        spill_time = datetime(2026, 8, 27, 4, 0)
        pings = [
            {"lon": 72.70, "lat": 18.80, "timestamp": (spill_time - timedelta(minutes=45)).isoformat(), "sog": 13.5, "cog": 45.0},
            {"lon": 72.80, "lat": 18.90, "timestamp": (spill_time + timedelta(minutes=15)).isoformat(), "sog": 4.5, "cog": 45.0},
            {"lon": 72.90, "lat": 19.00, "timestamp": (spill_time + timedelta(minutes=75)).isoformat(), "sog": 14.0, "cog": 45.0},
        ]
        cone = self._build_dummy_cone()

        recon = reconstruct_and_score_vessel(
            vessel_id="999000222",
            ais_fixes=pings,
            origin_cone_fc=cone,
            spill_time=spill_time,
        )

        assert recon.cpa_distance_km < 2.0
        assert recon.cpa_time_diff_hours <= 1.0
        assert recon.causal_veto is False, "Should not trigger causal veto"
        assert recon.ray_trace_score > 0.70, f"Expected high score, got {recon.ray_trace_score}"
        assert recon.speed_summary is not None
        assert recon.speed_summary["discharge_speed_window"] is True, "Detected 4.5 kn discharge speed"


class TestModelContracts4DFields:
    """Verification of Pydantic model serialization with 4D fields."""

    def test_candidate_4d_fields_serialization(self):
        trace = EvidenceTrace(
            proximity_score=0.85,
            path_match_score=0.90,
            cpa_distance_km=0.82,
            cpa_time_diff_hours=0.45,
            causal_veto=False,
            spatiotemporal_cpa_match=True,
        )

        cand = Candidate(
            vessel_id="413200100",
            vessel_name="MT OCEAN SENTINEL",
            last_known_position=[72.85, 18.95],
            suspicion_score=0.88,
            confidence_interval=[0.82, 0.94],
            evidence_trace=trace,
            cpa_distance_km=0.82,
            cpa_time_diff_hours=0.45,
            causal_veto=False,
            data_provenance="real_gfw",
        )

        cand_dict = cand.model_dump()
        assert cand_dict["cpa_distance_km"] == 0.82
        assert cand_dict["causal_veto"] is False
        assert cand_dict["evidence_trace"]["spatiotemporal_cpa_match"] is True
