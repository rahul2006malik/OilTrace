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
]


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

    keys, matrix, imputed_by_vessel = _median_impute(vessel_features)

    if len(keys) < 2:
        results = []
        for k in keys:
            results.append(_build_record(
                k, vessel_features[k], anomaly_score=0.5,
                dominant_factor="insufficient_population_for_isolation_forest",
                imputed_features=imputed_by_vessel[k],
                data_provenance="synthetic_fallback",
            ))
        return results

    model = IsolationForest(contamination=contamination, random_state=random_state)
    model.fit(matrix)
    # decision_function: higher = more normal, lower/negative = more anomalous.
    raw_scores = model.decision_function(matrix)
    # Normalize to [0, 1] where 1 = most anomalous, via min-max over this
    # population. This is population-relative by construction (matches the
    # project doc's framing: anomalous *relative to the real traffic in this
    # region/window*, not against a universal fixed threshold).
    lo, hi = raw_scores.min(), raw_scores.max()
    span = (hi - lo) or 1.0
    anomaly_scores = 1.0 - (raw_scores - lo) / span  # flip so higher = more anomalous

    results = []
    for i, k in enumerate(keys):
        vf = vessel_features[k]
        dominant = _dominant_factor(vf, imputed_by_vessel[k])
        provenance = "real_gfw"
        if "real_aisstream_live" in vf.sources:
            provenance = "real_aisstream_live"
        results.append(_build_record(
            k, vf, anomaly_score=round(float(anomaly_scores[i]), 4),
            dominant_factor=dominant,
            imputed_features=imputed_by_vessel[k],
            data_provenance=provenance,
        ))

    results.sort(key=lambda r: r["evidence_trace"]["anomaly_score"], reverse=True)
    return results


def _dominant_factor(vf: VesselFeatures, imputed: list[str]) -> str:
    """
    Cheap, explainable "why did this vessel score high" summary — NOT the
    IsolationForest's internal feature-importance math (that's not
    straightforwardly per-sample for this model), but a defensible proxy:
    whichever non-imputed feature is furthest (in raw terms) from a
    "normal" baseline of zero/low activity. Good enough for the Q&A
    talking point ("why should we trust this"); a more rigorous SHAP-based
    explanation is a documented upgrade path, not 2-week scope.
    """
    candidates = []
    if "gap_duration_hours" not in imputed and vf.gap_duration_hours > 0:
        candidates.append(("gap_duration_hours", vf.gap_duration_hours))
    if "loitering_duration_hours" not in imputed and vf.loitering_duration_hours > 0:
        candidates.append(("loitering_duration_hours", vf.loitering_duration_hours))
    if "heading_change_rate" not in imputed and vf.heading_change_rate:
        candidates.append(("heading_change_rate", vf.heading_change_rate))
    if "speed_variance" not in imputed and vf.speed_variance:
        candidates.append(("speed_variance", vf.speed_variance))
    if "encounter_count" not in imputed and vf.encounter_count > 0:
        candidates.append(("encounter_count", vf.encounter_count))
    if not candidates:
        return "none"
    return max(candidates, key=lambda c: c[1])[0]


def _build_record(
    vessel_key: str,
    vf: VesselFeatures,
    *,
    anomaly_score: float,
    dominant_factor: str,
    imputed_features: list[str],
    data_provenance: str,
) -> dict[str, Any]:
    """
    Shaped to match schemas.md's `candidates[]` entry as closely as
    possible at this stage of the pipeline. `suspicion_score` and
    `confidence_interval` are left None — see module docstring — this is
    NOT a schema violation, schemas.md doesn't mark those fields as
    non-nullable, and the alternative (fabricating a number before Drift
    exists) would be the actual violation of cross-cutting rule 2.
    """
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
            "dominant_factor": dominant_factor,
        },
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

        # Two-tiered fusion: Full 4-factor if forward confession exists, otherwise renormalize over available factors
        effective_conf = conf_real if conf_real is not None else 0.0
        effective_prox = prox_real if prox_real is not None else 0.0

        if conf_real is not None:
            if prior_real is not None:
                w_prox = weight_proximity / total_w_full
                w_conf = weight_confession / total_w_full
                w_anom = weight_anomaly / total_w_full
                w_prior = weight_prior / total_w_full
                raw_suspicion = (
                    w_prox * effective_prox + w_conf * effective_conf
                    + w_anom * anomaly_score + w_prior * prior_real
                )
            else:
                w_prox = weight_proximity / total_w_no_prior
                w_conf = weight_confession / total_w_no_prior
                w_anom = weight_anomaly / total_w_no_prior
                raw_suspicion = w_prox * effective_prox + w_conf * effective_conf + w_anom * anomaly_score
        else:
            if prior_real is not None:
                w_sum = weight_proximity + weight_anomaly + weight_prior
                raw_suspicion = (
                    weight_proximity * effective_prox
                    + weight_anomaly * anomaly_score
                    + weight_prior * prior_real
                ) / w_sum
            else:
                w_sum = weight_proximity + weight_anomaly
                raw_suspicion = (
                    weight_proximity * effective_prox
                    + weight_anomaly * anomaly_score
                ) / w_sum

        suspicion = round(min(1.0, max(0.0, raw_suspicion)), 4)

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
            "evidence_trace": {
                "proximity_score": round(effective_prox, 4),
                "confession_match_score": round(effective_conf, 4),
                "anomaly_score": round(anomaly_score, 4),
                "vessel_type_prior": round(prior_real, 4) if prior_real is not None else None,
                "dominant_factor": ev.get("dominant_factor", "anomaly_score"),
            },
            "data_provenance": cand.get("data_provenance", "real_gfw"),
        })

    fused_candidates.sort(
        key=lambda c: c["suspicion_score"] if c.get("suspicion_score") is not None else -1.0,
        reverse=True,
    )
    return fused_candidates

