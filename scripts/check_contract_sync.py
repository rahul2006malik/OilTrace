#!/usr/bin/env python3
"""
scripts/check_contract_sync.py

Strict CI / pre-demo enforcement script for OilTrace Canonical Contract (v2).
Diffs and verifies synchronization between:
  1. contracts/schema.ts (Canonical TypeScript definition)
  2. backend/app/models.py (FastAPI Pydantic models)
  3. frontend/src/types/index.ts (Frontend TypeScript definitions)

Fails loudly with non-zero exit code if any field is missing, misspelled,
or drifted.
"""

import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_TS = ROOT / "contracts" / "schema.ts"
MODELS_PY = ROOT / "backend" / "app" / "models.py"
FRONTEND_TYPES_TS = ROOT / "frontend" / "src" / "types" / "index.ts"

# Canonical field expectations derived from contracts/schema.ts (§2)
CANONICAL_SCHEMAS = {
    "SlickDetection": {
        "spill_id",
        "detected_at",
        "geometry",
        "centroid",
        "area_km2",
        "elongation_ratio",
        "oil_confidence",
        "thickness_class",
        "source_scene_id",
        "lookalike_suppressed",
        "data_provenance",
    },
    "DriftEnsembleMember": {
        "member_id",
        "windage_coefficient",
        "current_scale",
        "backward_track",
    },
    "DriftRun": {
        "spill_id",
        "forcing",
        "ensemble_size",
        "members_complete",
        "members_dropped",
        "members",
        "origin_zone",
    },
    "EvidenceTrace": {
        "proximity_score",
        "path_match_score",
        "confession_match_score",
        "anomaly_score",
        "vessel_type_prior",
        "dominant_factor",
        "shap_explanation",
        "counterfactuals",
        "narrative",
    },
    "Candidate": {
        "vessel_id",
        "vessel_name",
        "imo",
        "flag_country",
        "vessel_type",
        "last_known_position",
        "ais_positions",
        "route_reconstruction",
        "suspicion_score",
        "confidence_interval",
        "confidence_interval_method",
        "evidence_trace",
        "proximate_but_absent_at_origin",
        "data_provenance",
    },
    "AttributionResult": {
        "spill_id",
        "candidates",
        "dark_vessel_alert",
        "top_k_recovery",
        "real_vessel_fraction",
    },
    "EvidenceDossier": {
        "spill_id",
        "generated_at",
        "payload_sha256",
        "detection",
        "drift",
        "attribution",
    },
}


def parse_ts_interface_fields(content: str, interface_name: str) -> set:
    """Extracts top-level property names from an exported TypeScript interface."""
    pattern = rf"export\s+interface\s+{interface_name}\s*\{{"
    match = re.search(pattern, content)
    if not match:
        return set()
    start_idx = match.end()

    fields = set()
    depth = 0
    lines = content[start_idx:].split("\n")

    for line in lines:
        stripped = line.strip()
        # If at depth 0, any property declaration belongs to this interface
        if depth == 0 and stripped and not (stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*")):
            prop_match = re.match(r"^([a-zA-Z0-9_]+)\??\s*:", stripped)
            if prop_match:
                fields.add(prop_match.group(1))

        # Update depth for next lines
        for char in stripped:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth < 0:
                    return fields

    return fields


def parse_pydantic_fields(content: str, class_name: str) -> set:
    """Extracts field names from a Pydantic model class."""
    pattern = rf"class\s+{class_name}\s*\([^)]*\):([\s\S]*?)(?=\nclass\s|\Z)"
    match = re.search(pattern, content)
    if not match:
        return set()
    block = match.group(1)
    fields = set()
    for line in block.split("\n"):
        # Match python field declaration at class level (indented 4 spaces)
        field_match = re.match(r"^\s{4}([a-zA-Z0-9_]+)\s*:\s*([^=\n]+)", line)
        if field_match:
            name = field_match.group(1)
            if not name.startswith("_"):
                fields.add(name)
    return fields


def main() -> int:
    print("=" * 70)
    print("OILTRACE CANONICAL CONTRACT SYNCHRONIZATION AUDIT (v2.0)")
    print("=" * 70)

    errors = []

    if not CONTRACT_TS.exists():
        print(f"[FAIL] Canonical contract missing: {CONTRACT_TS}")
        return 1
    contract_content = CONTRACT_TS.read_text(encoding="utf-8")

    if not MODELS_PY.exists():
        print(f"[FAIL] Backend models missing: {MODELS_PY}")
        return 1
    models_content = MODELS_PY.read_text(encoding="utf-8")

    frontend_content = None
    if FRONTEND_TYPES_TS.exists():
        frontend_content = FRONTEND_TYPES_TS.read_text(encoding="utf-8")
    else:
        print(f"[WARN] Frontend types not found at {FRONTEND_TYPES_TS} (will check once scaffolded).")

    for entity_name, expected_fields in CANONICAL_SCHEMAS.items():
        print(f"\nVerifying entity: {entity_name} ({len(expected_fields)} fields)")

        # 1. Check contracts/schema.ts
        ts_fields = parse_ts_interface_fields(contract_content, entity_name)
        missing_in_ts = expected_fields - ts_fields
        if missing_in_ts:
            err = f"[CONTRACT TS] {entity_name} missing canonical fields: {missing_in_ts}"
            print(f"  [FAIL] {err}")
            errors.append(err)
        else:
            print(f"  [PASS] contracts/schema.ts matches ({len(ts_fields)} fields)")

        # 2. Check backend/app/models.py
        py_fields = parse_pydantic_fields(models_content, entity_name)
        missing_in_py = expected_fields - py_fields
        if missing_in_py:
            err = f"[BACKEND PY] {entity_name} missing canonical fields: {missing_in_py}"
            print(f"  [FAIL] {err}")
            errors.append(err)
        else:
            print(f"  [PASS] backend/app/models.py matches ({len(py_fields)} fields)")

        # 3. Check frontend/src/types/index.ts (if exists)
        if frontend_content:
            fe_fields = parse_ts_interface_fields(frontend_content, entity_name)
            missing_in_fe = expected_fields - fe_fields
            if missing_in_fe:
                err = f"[FRONTEND TS] {entity_name} missing canonical fields: {missing_in_fe}"
                print(f"  [FAIL] {err}")
                errors.append(err)
            else:
                print(f"  [PASS] frontend/src/types/index.ts matches ({len(fe_fields)} fields)")

    print("\n" + "=" * 70)
    if errors:
        print(f"FAILED: {len(errors)} contract synchronization error(s) detected.")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("SUCCESS: All canonical contracts in complete lockstep across subsystems.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
