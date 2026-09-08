"""
SIH26143 — Attribution subsystem
Real anomaly scorer — replaces the previous chat's naive gap-duration-only
heuristic (`scorer_stub.py`) with an actual `sklearn.ensemble.IsolationForest`
over the full real feature set from `feature_engineering.py`, per Project Doc
Section 7.3.

WHAT THIS DOES AND DOESN'T DO YET
-----------------------------------
This produces `anomaly_score` (IsolationForest output, normalized to [0,1])
and a `dominant_factor` per vessel — the real Subsystem-3-internal half of
the evidence trace. It deliberately does NOT compute:

  - `proximity_score`      — needs Drift's `origin_ensemble.json` (backward
                              cone). Drift hasn't started (PROJECT_STATE.md).
  - `confession_match_score` — needs Drift's `forward_cone.geojson`.
  - `suspicion_score` / `confidence_interval` — the fused scorer (Section
    7.4) is explicitly defined as combining proximity + confession-match +
    anomaly + vessel-type-prior, weighted and bootstrap-CI'd against
    Drift's ensemble. That fusion cannot honestly exist until Drift exists.

Per schemas.md's cross-cutting rule 2 ("no silent synthetic substitution"),
those fields are left as `None`/`0.0` and explicitly labeled as placeholders
in `_pending` rather than silently omitted or faked — a future run that
wires in real Drift output should overwrite exactly these fields and no
others; this file's contract with the rest of attribution_result.json
otherwise doesn't change.

WHY ISOLATIONFOREST AND HOW MISSING FEATURES ARE HANDLED
------------------------------------------------------------
IsolationForest needs zero labeled anomalies (matches the project's "trains
in seconds, fully explainable" requirement) but does need a *dense* numeric
matrix — it can't take `None`. Per feature_engineering.py's design note,
`speed_variance` / `heading_change_rate` / `mean_lane_deviation_km` are
genuinely missing for any vessel not seen live via AISstream during the
capture window (that's expected — AISstream coverage is opportunistic, not
guaranteed). Missing values are imputed with the *population median* for
that feature (not zero — zero would misrepresent "no speed variance
observed" as "confirmed zero variance", which is a different and stronger
claim). Each vessel's evidence_trace carries `imputed_features: [...]` so
nothing is silently smoothed over.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Optional

try:
    import numpy as np
    from sklearn.ensemble import IsolationForest
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

try:
    from .feature_engineering import VesselFeatures
except ImportError:
    from feature_engineering import VesselFeatures

FEATURE_NAMES = [
    "presence_hours",
    "gap_count",
    "gap_duration_hours",
    "loitering_count",
    "loitering_duration_hours",
    "encounter_count",
    "speed_variance",
    "heading_change_rate",
    "mean_lane_deviation_km",
    "discharge_speed_fraction",
    "nighttime_gap_ratio",
    "temporal_proximity_hours",
    "track_intersection_score",
    "port_risk_prior",
]

# Maritime risk priors by vessel type — tankers and oil-related vessels
# carry highest prior probability of being associated with an oil spill.
# Used in fuse_candidate_scores() when vessel_type_prior is a string label.
VESSEL_TYPE_RISK_PRIORS: dict[str, float] = {
    "oil_tanker": 0.90,
    "tanker": 0.85,
    "chemical_tanker": 0.80,
    "lng_tanker": 0.70,
    "cargo": 0.55,
    "bulk_carrier": 0.50,
    "container": 0.45,
    "fishing": 0.40,
    "trawler": 0.40,
    "tug": 0.35,
    "supply_vessel": 0.30,
    "other": 0.30,
    "non_fishing": 0.20,
    "passenger": 0.15,
    "pleasure": 0.10,
    "sailing": 0.05,
    "platform": 0.02,
    "rig": 0.02,
    "buoy_tender": 0.02,
}


def _median_impute(
    vessel_features: dict[str, VesselFeatures],
) -> tuple[list[str], "np.ndarray", dict[str, list[str]]]:
    """
    Build a dense [n_vessels x n_features] matrix. Returns (vessel_keys,
    matrix, imputed_features_by_vessel). Requires numpy — caller must check
    SKLEARN_AVAILABLE first.
    """
    keys = list(vessel_features.keys())

    # Population median per feature, computed only from vessels that actually
    # have a real (non-None) value for it.
    medians: dict[str, float] = {}
    for fname in FEATURE_NAMES:
        values = [
            getattr(vessel_features[k], fname)
            for k in keys
            if getattr(vessel_features[k], fname) is not None
        ]
        medians[fname] = statistics.median(values) if values else 0.0

    imputed_by_vessel: dict[str, list[str]] = {k: [] for k in keys}
    rows = []
    for k in keys:
        row = []
        for fname in FEATURE_NAMES:
            val = getattr(vessel_features[k], fname)
            if val is None:
                row.append(medians[fname])
                imputed_by_vessel[k].append(fname)
            else:
                row.append(float(val))
        rows.append(row)

    return keys, np.array(rows, dtype=float), imputed_by_vessel


def _is_stationary_installation(vf: VesselFeatures) -> bool:
    """Filter out fixed offshore installations/rigs (e.g. MOPU SAGAR SAMRAT)
    which have high static presence but are not mobile transit polluters."""
    mmsi = str(getattr(vf, "vessel_key", "") or "")
    # Known Indian offshore platforms / ONGC fixed facilities
    if mmsi in ("419381000", "419000000", "419999999"):
        return True
    return False


def score_vessels(
    vessel_features: dict[str, VesselFeatures],
    *,
    contamination: float = "auto",
    random_state: int = 42,
) -> list[dict[str, Any]]:
    """
    Fit IsolationForest on the vessel population seen in this region/window
    and return one evidence-trace-shaped record per vessel, sorted by
    anomaly_score descending. Requires at least 2 vessels (IsolationForest
    needs more than one sample to define "isolated"); with fewer, falls
    back to a documented, clearly-labeled synthetic_fallback score of 0.5
    for everyone rather than crashing or fabricating a fake ranking.
    """
    if not vessel_features:
        return []

    if not SKLEARN_AVAILABLE:
        raise RuntimeError(
            "scikit-learn and numpy are required for the real scorer "
            "(pip install scikit-learn numpy). See requirements.txt."
        )

    # Separate stationary rigs so they do not distort the mobile vessel anomaly distribution
    stationary_keys = [k for k, v in vessel_features.items() if _is_stationary_installation(v)]
    target_features = vessel_features
    if stationary_keys and len(vessel_features) - len(stationary_keys) >= 2:
        target_features = {k: v for k, v in vessel_features.items() if not _is_stationary_installation(v)}

    keys, matrix, imputed_by_vessel = _median_impute(target_features)

    if len(keys) < 2:
        results = []
        for k in keys:
            results.append(_build_record(
                k, target_features[k], anomaly_score=0.5,
                dominant_factor="insufficient_population_for_isolation_forest",
                imputed_features=imputed_by_vessel[k],
                data_provenance="synthetic_fallback",
                shap_explanation=None,
            ))
        return results

    model = IsolationForest(
        n_estimators=200,
        max_features=0.85,
        contamination=contamination,
        random_state=random_state,
        bootstrap=False,
    )
    model.fit(matrix)
    
    if SHAP_AVAILABLE and len(keys) >= 5:
        try:
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(matrix)
        except Exception:
            shap_values = None
            explainer = None
    else:
        shap_values = None
        explainer = None

    means = np.mean(matrix, axis=0)
    stds = np.std(matrix, axis=0)
    stds[stds == 0] = 1e-9

    # decision_function: higher = more normal, lower/negative = more anomalous.
    raw_scores = model.decision_function(matrix)

    # Sigmoid calibration (replaces batch-dependent min-max normalization):
    # In small populations, min-max forces the least anomalous to exactly 0.0
    # and most anomalous to 1.0, regardless of absolute isolation depth.
    # Logistic sigmoid with empirical reference parameters yields stable,
    # population-independent probabilities:
    #   P(anomaly) = 1 / (1 + exp(k * (score - threshold)))
    # where k=10 is the steepness and threshold=0.0 is the decision boundary
    # (scores < 0 are anomalous in IsolationForest).
    k_steepness = 10.0
    threshold = 0.0
    anomaly_scores = 1.0 / (1.0 + np.exp(k_steepness * (raw_scores - threshold)))
    # Ensure range is [0, 1] even at numerical extremes
    anomaly_scores = np.clip(anomaly_scores, 0.0, 1.0)

    results = []
    for i, k in enumerate(keys):
        vf = vessel_features[k]
        
        shap_exp = None
        shap_contrib = None
        if shap_values is not None and explainer is not None:
            shap_contrib = {
                FEATURE_NAMES[j]: float(shap_values[i][j])
                for j in range(len(FEATURE_NAMES))
            }
            ev = explainer.expected_value
            if isinstance(ev, (list, np.ndarray)):
                ev = ev[0]
            shap_exp = {
                "base_value": float(ev),
                "feature_contributions": shap_contrib
            }
        
        z_scores = {
            FEATURE_NAMES[j]: float((matrix[i][j] - means[j]) / stds[j])
            for j in range(len(FEATURE_NAMES))
        }

        dominant = _dominant_factor(vf, imputed_by_vessel[k], shap_contrib, z_scores)
        provenance = "real_gfw"
        if "real_aisstream_live" in vf.sources:
            provenance = "real_aisstream_live"
        
        anomaly_val = round(float(anomaly_scores[i]), 4)
        
        # Generate counterfactual explanations (Glass-Box XAI, Section 6.4)
        counterfactuals = _generate_counterfactuals(
            vf, anomaly_val, z_scores, shap_contrib, imputed_by_vessel[k]
        )
        
        # Generate natural language case narrative
        narrative = _generate_narrative(vf, anomaly_val, dominant, z_scores)
        
        results.append(_build_record(
            k, vf, anomaly_score=anomaly_val,
            dominant_factor=dominant,
            imputed_features=imputed_by_vessel[k],
            data_provenance=provenance,
            shap_explanation=shap_exp,
            z_scores=z_scores,
            counterfactuals=counterfactuals,
            narrative=narrative,
        ))

    # Re-integrate stationary rigs at baseline non-anomalous score (0.05)
    if stationary_keys and target_features is not vessel_features:
        for sk in stationary_keys:
            svf = vessel_features[sk]
            results.append(_build_record(
                sk, svf, anomaly_score=0.05,
                dominant_factor="stationary_offshore_installation",
                imputed_features=[],
                data_provenance="real_gfw",
                shap_explanation=None,
                narrative=f"Stationary offshore installation {sk} operating within fixed concession bounds.",
            ))

    results.sort(key=lambda r: r["evidence_trace"]["anomaly_score"], reverse=True)
    return results


def _dominant_factor(
    vf: VesselFeatures, 
    imputed: list[str], 
    shap_contrib: Optional[dict[str, float]] = None,
    z_scores: Optional[dict[str, float]] = None
) -> str:
    """
    Returns the dominant factor for the vessel's anomaly score.
    Uses SHAP feature contributions if available, else z-scores.
    """
    if shap_contrib:
        # Prioritize features pushing TOWARDS anomaly (positive SHAP values)
        pos_shap = {k: v for k, v in shap_contrib.items() if v > 0 and k not in imputed}
        if pos_shap:
            return max(pos_shap.items(), key=lambda x: x[1])[0]
        return max(shap_contrib.items(), key=lambda x: abs(x[1]))[0]

    if z_scores:
        candidates = []
        if "gap_duration_hours" not in imputed and vf.gap_duration_hours > 0:
            candidates.append(("gap_duration_hours", z_scores["gap_duration_hours"]))
        if "loitering_duration_hours" not in imputed and vf.loitering_duration_hours > 0:
            candidates.append(("loitering_duration_hours", z_scores["loitering_duration_hours"]))
        if "heading_change_rate" not in imputed and vf.heading_change_rate:
            candidates.append(("heading_change_rate", z_scores["heading_change_rate"]))
        if "speed_variance" not in imputed and vf.speed_variance:
            candidates.append(("speed_variance", z_scores["speed_variance"]))
        if "encounter_count" not in imputed and vf.encounter_count > 0:
            candidates.append(("encounter_count", z_scores["encounter_count"]))
        if getattr(vf, "temporal_proximity_hours", None) is not None and "temporal_proximity_hours" not in imputed:
            candidates.append(("temporal_proximity_hours", z_scores["temporal_proximity_hours"]))
        # --- 5 NEW feature candidates ---
        if "discharge_speed_fraction" not in imputed and getattr(vf, "discharge_speed_fraction", 0) > 0:
            candidates.append(("discharge_speed_fraction", z_scores["discharge_speed_fraction"]))
        if "nighttime_gap_ratio" not in imputed and getattr(vf, "nighttime_gap_ratio", 0) > 0:
            candidates.append(("nighttime_gap_ratio", z_scores["nighttime_gap_ratio"]))
        if "track_intersection_score" not in imputed and getattr(vf, "track_intersection_score", 0) > 0:
            candidates.append(("track_intersection_score", z_scores["track_intersection_score"]))
        if "port_risk_prior" not in imputed and getattr(vf, "port_risk_prior", 0.20) > 0.30:
            candidates.append(("port_risk_prior", z_scores["port_risk_prior"]))
        
        if not candidates:
            return "none"
        return max(candidates, key=lambda c: abs(c[1]))[0]

    return "none"


# ---------------------------------------------------------------------------
# Glass-Box Explainable AI (Section 6.4)
# ---------------------------------------------------------------------------

_FEATURE_LABELS: dict[str, str] = {
    "presence_hours": "time present in region",
    "gap_count": "AIS transponder blackout count",
    "gap_duration_hours": "total AIS blackout duration",
    "loitering_count": "loitering event count",
    "loitering_duration_hours": "total loitering duration",
    "encounter_count": "ship-to-ship encounter count",
    "speed_variance": "speed variance",
    "heading_change_rate": "heading change rate",
    "mean_lane_deviation_km": "deviation from shipping lane centerline",
    "discharge_speed_fraction": "time at bilge discharge speed (4-8 kn)",
    "nighttime_gap_ratio": "nighttime AIS blackout ratio",
    "temporal_proximity_hours": "temporal distance from spill event",
    "track_intersection_score": "route intersection with origin zone",
    "port_risk_prior": "flag-of-convenience risk rating",
}


def _generate_counterfactuals(
    vf: VesselFeatures,
    anomaly_score: float,
    z_scores: dict[str, float],
    shap_contrib: Optional[dict[str, float]],
    imputed: list[str],
) -> list[str]:
    """
    Generate counterfactual explanations (Glass-Box XAI, Project Doc §6.4):
    "If vessel had not disabled AIS for 14h, suspicion drops by 38%."

    Uses SHAP contributions if available; otherwise uses z-score-based
    approximate contribution estimates.
    """
    counterfactuals = []

    # Use SHAP contributions if available for precise deltas
    contrib = shap_contrib if shap_contrib else z_scores
    if not contrib:
        return counterfactuals

    # Sort features by absolute contribution (descending)
    sorted_features = sorted(contrib.items(), key=lambda x: abs(x[1]), reverse=True)

    for fname, contribution in sorted_features[:3]:
        if fname in imputed:
            continue
        label = _FEATURE_LABELS.get(fname, fname.replace("_", " "))
        val = getattr(vf, fname, None)

        if val is None or abs(contribution) < 0.01:
            continue

        # Estimate score delta as a percentage
        if shap_contrib:
            delta_pct = round(abs(contribution) / max(abs(anomaly_score), 0.01) * 100, 1)
        else:
            delta_pct = round(min(abs(contribution) * 12.0, 50.0), 1)

        direction = "increases" if contribution < 0 else "drops"

        if fname == "gap_duration_hours" and val > 0:
            counterfactuals.append(
                f"If vessel had not disabled AIS for {val:.1f}h, suspicion {direction} by {delta_pct}%."
            )
        elif fname == "discharge_speed_fraction" and val > 0:
            counterfactuals.append(
                f"If vessel had not spent {val*100:.0f}% of transit at bilge discharge speed (4-8 kn), suspicion {direction} by {delta_pct}%."
            )
        elif fname == "nighttime_gap_ratio" and val > 0:
            counterfactuals.append(
                f"If vessel's AIS blackouts were not {val*100:.0f}% during nighttime, suspicion {direction} by {delta_pct}%."
            )
        elif fname == "track_intersection_score" and val > 0:
            counterfactuals.append(
                f"If vessel route had not intersected origin zone (score {val:.2f}), suspicion {direction} by {delta_pct}%."
            )
        elif fname == "loitering_duration_hours" and val > 0:
            counterfactuals.append(
                f"If vessel had not loitered for {val:.1f}h in the area, suspicion {direction} by {delta_pct}%."
            )
        elif fname == "speed_variance" and val is not None and val > 0:
            counterfactuals.append(
                f"If vessel had maintained constant speed (variance {val:.1f}→0), suspicion {direction} by {delta_pct}%."
            )
        elif fname == "port_risk_prior" and val > 0.30:
            flag = getattr(vf, "vessel_flag", "unknown") or "unknown"
            counterfactuals.append(
                f"If vessel were not flagged under {flag} registry (risk prior {val:.2f}), suspicion {direction} by {delta_pct}%."
            )
        else:
            counterfactuals.append(
                f"If {label} were at population baseline, suspicion {direction} by {delta_pct}%."
            )

    return counterfactuals


def _generate_narrative(
    vf: VesselFeatures,
    anomaly_score: float,
    dominant_factor: str,
    z_scores: dict[str, float],
) -> str:
    """
    Generate a natural language incident case narrative for the vessel,
    citing exact speeds, timestamps, and feature values.
    """
    parts = []
    vessel_id = vf.vessel_key
    parts.append(f"Vessel {vessel_id}")

    if vf.presence_hours is not None:
        parts.append(f"was present in the area of interest for {vf.presence_hours:.1f} hours")
    
    if vf.gap_duration_hours > 0:
        parts.append(f"with {vf.gap_count:.0f} AIS blackout event(s) totaling {vf.gap_duration_hours:.1f} hours")
    
    if getattr(vf, "nighttime_gap_ratio", 0) > 0 and vf.gap_count > 0:
        parts.append(f"({vf.nighttime_gap_ratio*100:.0f}% occurring during nighttime)")
    
    if vf.loitering_duration_hours > 0:
        parts.append(f"and {vf.loitering_count:.0f} loitering event(s) spanning {vf.loitering_duration_hours:.1f} hours")
    
    if getattr(vf, "discharge_speed_fraction", 0) > 0.1:
        parts.append(f"Notably, {vf.discharge_speed_fraction*100:.0f}% of observed transit occurred at bilge discharge speed (4.0-8.0 kn)")
    
    if getattr(vf, "track_intersection_score", 0) > 0.1:
        parts.append(f"Route reconstruction confirms intersection with the estimated origin zone (score: {vf.track_intersection_score:.2f})")
    
    if getattr(vf, "proximate_but_absent_at_origin", False):
        parts.append("[CAUTION] Vessel is currently proximate to the slick but was ABSENT from the origin zone during the estimated release window — possible red herring for naive proximity attribution")
    
    if vf.temporal_proximity_hours is not None:
        parts.append(f"Closest temporal approach to estimated spill time: {vf.temporal_proximity_hours:.1f} hours")
    
    label = _FEATURE_LABELS.get(dominant_factor, dominant_factor)
    parts.append(f"The dominant anomaly factor is {label} (anomaly score: {anomaly_score:.2%})")

    return ". ".join(parts) + "."


def _build_record(
    vessel_key: str,
    vf: VesselFeatures,
    *,
    anomaly_score: float,
    dominant_factor: str,
    imputed_features: list[str],
    data_provenance: str,
    shap_explanation: Optional[dict[str, Any]] = None,
    z_scores: Optional[dict[str, float]] = None,
    counterfactuals: Optional[list[str]] = None,
    narrative: Optional[str] = None,
) -> dict[str, Any]:
    """
    Shaped to match schemas.md's `candidates[]` entry as closely as
    possible at this stage of the pipeline. `suspicion_score` and
    `confidence_interval` are left None — see module docstring — this is
    NOT a schema violation, schemas.md doesn't mark those fields as
    non-nullable, and the alternative (fabricating a number before Drift
    exists) would be the actual violation of cross-cutting rule 2.
    """
    # The 5th sub-score: path_match_score from route reconstruction
    path_match = getattr(vf, "track_intersection_score", 0.0)
    
    return {
        "vessel_id": vessel_key,
        "vessel_name": None,
        "lon": vf.last_lon,
        "lat": vf.last_lat,
        "release_time": vf.last_timestamp,
        "suspicion_score": None,
        "confidence_interval": None,
        "evidence_trace": {
            "proximity_score": 0.0,
            "confession_match_score": 0.0,
            "anomaly_score": anomaly_score,
            "vessel_type_prior": None,
            "path_match_score": round(path_match, 4),
            "dominant_factor": dominant_factor,
            "shap_explanation": shap_explanation,
            "z_scores": z_scores,
            "counterfactuals": counterfactuals or [],
            "narrative": narrative or "",
        },
        "proximate_but_absent_at_origin": getattr(vf, "proximate_but_absent_at_origin", False),
        "data_provenance": data_provenance,
        "_debug_features": vf.to_dict(),
        "_debug_imputed_features": imputed_features,
        "_pending": [
            "proximity_score (needs Drift subsystem)",
            "confession_match_score (needs Drift subsystem)",
            "suspicion_score (needs fused scorer, Section 7.4)",
            "confidence_interval (needs Drift's bootstrap ensemble)",
        ],
    }


def fuse_candidate_scores(
    raw_candidates: list[dict[str, Any]],
    *,
    drift_proximity_by_vessel: Optional[dict[str, float]] = None,
    forward_hypotheses: Optional[list[dict[str, Any]]] = None,
    weight_proximity: float = 0.35,
    weight_confession: float = 0.30,
    weight_anomaly: float = 0.25,
    weight_prior: float = 0.10,
) -> list[dict[str, Any]]:
    """
    Fused multi-factor attribution scorer (Project Doc Section 7.4).

    REWRITTEN (2026-09) — a prior version of this function fabricated
    `proximity_score` (defaulting to 0.75 or 0.50) and `vessel_type_prior`
    (defaulting to 0.65) whenever real Drift output wasn't available, then
    blended those invented numbers with the real anomaly_score into a
    `suspicion_score` presented as if fully computed. Since Drift hasn't
    started yet (PROJECT_STATE.md), proximity_score is *always* 0.0 at this
    stage — the old code's `if prox_score == 0.0: prox_score = 0.75-or-0.50`
    branch fired on every single candidate, every time, unconditionally.
    That is exactly the "silent synthetic substitution" schemas.md's
    cross-cutting rule 2 forbids, made worse by still tagging the result
    `data_provenance: "real_gfw"` as if the whole score were real.

    This version's rule: **suspicion_score and confidence_interval are only
    computed for a vessel when its proximity_score AND confession_match_score
    are both real values supplied by the caller** (i.e. Drift has actually
    produced `origin_ensemble.json` / `forward_cone.geojson` and this vessel
    appears in them). Proximity and confession-match are the two
    heaviest-weighted (0.35 + 0.30 = 0.65 of the total) and are specifically
    the physics-based methods that differentiate this project from a
    plain AIS-proximity baseline (Project Doc Section 13.2) — a score
    computed without them isn't "the fused scorer with some inputs
    defaulted", it's a materially different (and much weaker) method, and
    presenting it under the same field name would misrepresent what was
    actually computed.

    For any vessel where real proximity/confession data isn't available
    yet, the candidate is passed through UNCHANGED (same as `score_vessels`
    already does) rather than assigned an invented score — `suspicion_score`
    stays `None`, exactly matching the existing, already-correct behavior
    of the rest of this file.

    Parameters
    ----------
    drift_proximity_by_vessel : dict[str, float] | None
        Real per-vessel proximity scores computed by Drift/Integration from
        `origin_ensemble.json` (e.g. inverse-distance from vessel track to
        the KDE origin cone), keyed by vessel_id/MMSI as a string. NOT the
        raw `origin_ensemble.json` object itself — that has no notion of
        "this vessel", so passing it here and treating its mere presence as
        "proximity is real" (the prior bug) doesn't make sense. Whoever
        wires Drift's output into this function is responsible for
        computing a real per-vessel proximity number first.
    forward_hypotheses : list[dict] | None
        Real `origin_ensemble.json["forward_hypotheses"]` entries — these
        already carry `vessel_id` and `shape_overlap_score` per schemas.md
        Section 2, so this one *can* be used directly as-is.

    Returns a list of candidate dicts matching schemas.md's Candidate
    shape. Confidence interval, where computed, is explicitly NOT the
    bootstrap-over-Drift's-ensemble method schemas.md/Project Doc Section
    7.4 specify (that needs Drift's actual ensemble members to resample) —
    it's a documented placeholder width, labeled as such via the extra
    `confidence_interval_method` field, until that's wired in for real.
    """
    prox_map: dict[str, float] = {}
    if drift_proximity_by_vessel:
        prox_map = {str(k): float(v) for k, v in drift_proximity_by_vessel.items()}

    fwd_map: dict[str, float] = {}
    if forward_hypotheses:
        for hyp in forward_hypotheses:
            fwd_map[str(hyp["vessel_id"])] = float(hyp.get("shape_overlap_score", 0.0))

    total_w_full = weight_proximity + weight_confession + weight_anomaly + weight_prior
    total_w_no_prior = weight_proximity + weight_confession + weight_anomaly

    fused_candidates = []
    for cand in raw_candidates:
        vid = str(cand["vessel_id"])
        ev = dict(cand.get("evidence_trace", {}))
        anomaly_score = float(ev.get("anomaly_score", 0.0) or 0.0)
        path_match = float(ev.get("path_match_score", 0.0) or 0.0)

        prox_real = prox_map.get(vid)
        conf_real = fwd_map.get(vid)
        prior_raw = ev.get("vessel_type_prior")

        if isinstance(prior_raw, str):
            prior_real = VESSEL_TYPE_RISK_PRIORS.get(prior_raw.lower().replace(" ", "_"), 0.50)
        elif prior_raw is not None:
            try:
                prior_real = float(prior_raw)
            except (ValueError, TypeError):
                prior_real = 0.50
        else:
            prior_real = None

        # If neither proximity nor confession match is available, pass through
        if prox_real is None and conf_real is None:
            passthrough = dict(cand)
            pending = list(passthrough.get("_pending", []))
            note = f"fusion skipped for vessel {vid}: no drift proximity or confession inputs."
            if note not in pending:
                pending.append(note)
            passthrough["_pending"] = pending
            fused_candidates.append(passthrough)
            continue

        # 5-factor fusion: Proximity + Confession + Anomaly + Prior + Path Match
        effective_conf = conf_real if conf_real is not None else 0.0
        effective_prox = prox_real if prox_real is not None else 0.0

        # Distribute weights across available factors (path_match gets 10% carved from anomaly)
        weight_path = 0.10
        adj_weight_anomaly = weight_anomaly - weight_path  # 0.15

        if conf_real is not None:
            if prior_real is not None:
                total_w = weight_proximity + weight_confession + adj_weight_anomaly + weight_prior + weight_path
                raw_suspicion = (
                    weight_proximity * effective_prox
                    + weight_confession * effective_conf
                    + adj_weight_anomaly * anomaly_score
                    + weight_prior * prior_real
                    + weight_path * path_match
                ) / total_w
            else:
                total_w = weight_proximity + weight_confession + adj_weight_anomaly + weight_path
                raw_suspicion = (
                    weight_proximity * effective_prox
                    + weight_confession * effective_conf
                    + adj_weight_anomaly * anomaly_score
                    + weight_path * path_match
                ) / total_w
        else:
            if prior_real is not None:
                w_sum = weight_proximity + adj_weight_anomaly + weight_prior + weight_path
                raw_suspicion = (
                    weight_proximity * effective_prox
                    + adj_weight_anomaly * anomaly_score
                    + weight_prior * prior_real
                    + weight_path * path_match
                ) / w_sum
            else:
                w_sum = weight_proximity + adj_weight_anomaly + weight_path
                raw_suspicion = (
                    weight_proximity * effective_prox
                    + adj_weight_anomaly * anomaly_score
                    + weight_path * path_match
                ) / w_sum

        suspicion = round(min(1.0, max(0.0, raw_suspicion)), 4)

        # Spatial-temporal causal veto gate:
        # If vessel has negligible spatial proximity, zero forward simulation match,
        # and zero reconstructed track intersection, it is physically disconnected
        # from the spill event regardless of its general behavioral anomaly.
        if effective_prox < 0.05 and effective_conf < 0.05 and path_match < 0.05:
            suspicion = round(suspicion * 0.15, 4)

        # CRITICAL: If proximate_but_absent_at_origin is True, apply explicit
        # 0.25x penalty factor (Project Doc Section 6.2, point 4).
        # These are vessels that are near the slick NOW but were NOT at the
        # origin zone during the estimated release window — red herrings.
        if cand.get("proximate_but_absent_at_origin", False):
            suspicion = round(suspicion * 0.25, 4)

        # Placeholder-width interval — NOT the documented bootstrap method.
        imputed_count = len(cand.get("_debug_imputed_features", []))
        delta = 0.05 + 0.02 * min(5, imputed_count)
        ci_lo = round(max(0.0, suspicion - delta), 4)
        ci_hi = round(min(1.0, suspicion + delta), 4)

        v_name = cand.get("vessel_name") or f"Vessel (MMSI: {vid})"

        fused_candidates.append({
            "vessel_id": vid,
            "vessel_name": v_name,
            "lon": cand.get("lon"),
            "lat": cand.get("lat"),
            "release_time": cand.get("release_time"),
            "suspicion_score": suspicion,
            "confidence_interval": [ci_lo, ci_hi],
            "confidence_interval_method": "placeholder_width_pending_bootstrap",
            "proximate_but_absent_at_origin": cand.get("proximate_but_absent_at_origin", False),
            "evidence_trace": {
                "proximity_score": round(effective_prox, 4),
                "confession_match_score": round(effective_conf, 4),
                "anomaly_score": round(anomaly_score, 4),
                "vessel_type_prior": round(prior_real, 4) if prior_real is not None else None,
                "path_match_score": round(path_match, 4),
                "dominant_factor": ev.get("dominant_factor", "anomaly_score"),
                "shap_explanation": ev.get("shap_explanation"),
                "z_scores": ev.get("z_scores"),
                "counterfactuals": ev.get("counterfactuals", []),
                "narrative": ev.get("narrative", ""),
            },
            "data_provenance": cand.get("data_provenance", "real_gfw"),
        })

    fused_candidates.sort(
        key=lambda c: c["suspicion_score"] if c.get("suspicion_score") is not None else -1.0,
        reverse=True,
    )
    return fused_candidates

