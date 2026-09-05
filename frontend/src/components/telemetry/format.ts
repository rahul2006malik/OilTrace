/**
 * Formatting helpers for the Left Intelligence Panel.
 *
 * Provides date, coordinate, and metric formatting helpers.
 */

const MONTHS = [
  "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
];

/**
 * `2026-08-25T06:00:00Z` -> `25 AUG 2026, 06:00 UTC`
 * Falls back to the raw string if it can't be parsed, rather than throwing —
 * a malformed timestamp is a telemetry fact worth surfacing, not hiding.
 */
export function formatDetectedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const day = String(d.getUTCDate()).padStart(2, "0");
  const month = MONTHS[d.getUTCMonth()];
  const year = d.getUTCFullYear();
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${day} ${month} ${year}, ${hh}:${mm} UTC`;
}

/**
 * `[64.7986, 18.5805]` (lon, lat — schemas.md LonLat convention) ->
 * `[64.7986°E, 18.5805°N]`, flipping the hemisphere letter for negative
 * values rather than emitting a bare minus sign.
 */
export function formatCentroid(centroid: [number, number]): string {
  const [lon, lat] = centroid;
  const lonHem = lon < 0 ? "W" : "E";
  const latHem = lat < 0 ? "S" : "N";
  return `[${Math.abs(lon).toFixed(4)}°${lonHem}, ${Math.abs(lat).toFixed(4)}°${latHem}]`;
}

export function formatArea(areaKm2: number): string {
  return `${areaKm2.toFixed(2)} km²`;
}

export function formatElongation(ratio: number): string {
  return `${ratio.toFixed(2)}x`;
}

export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

/**
 * `00000.tif` + a raw scene id from the detection contract -> the
 * `S1A_IW_GRDH_00000`-style product tag used in the telemetry readout.
 * The backend's `source_scene_id` today is the bare batch index (e.g.
 * `"00000"`); this pads it into the display convention rather than
 * fabricating a product identifier that isn't in the contract.
 */
export function formatSourceSceneId(sourceSceneId: string): string {
  if (/^S1[A-D]_/i.test(sourceSceneId)) return sourceSceneId.toUpperCase();
  return `S1C_IW_GRDH_${sourceSceneId}`;
}

/**
 * `POST /detection/predict` (schemas.md §4 / DESIGN_SPEC §2.1) responds with
 * `{ has_oil, oil_confidence, geojson, execution_time_seconds }` — it does
 * not itself guarantee the full `SlickDetection` shape (spill_id, area_km2,
 * elongation_ratio, thickness_class, ...). The only concrete example on hand,
 * `sample_slick_detection.geojson`, is a *flat* SlickDetection object rather
 * than a FeatureCollection, which reads as the detector's real output shape.
 *
 * This adapter accepts either form so the telemetry panel doesn't break if
 * the wire format is the flat object, a FeatureCollection with the full
 * field set on `features[0].properties`, or a bare geometry — and never
 * silently fabricates fields it can't find (missing numeric fields surface
 * as `null` in `SpillGeometryCard`, not as invented zeros).
 */
export function normalizeDetectionResponse(
  raw: Record<string, unknown>,
  fallback: { spillId: string; sourceSceneId: string },
): Record<string, unknown> {
  const geojson = raw.geojson as Record<string, unknown> | undefined;

  // Case 1: already a flat SlickDetection-shaped object (has spill_id).
  if (geojson && typeof geojson === "object" && "spill_id" in geojson) {
    return geojson;
  }

  // Case 2: FeatureCollection — pull geometry + properties off feature 0.
  if (geojson && geojson.type === "FeatureCollection") {
    const features = (geojson.features as Array<Record<string, unknown>>) ?? [];
    const feature = features[0] ?? {};
    const properties = (feature.properties as Record<string, unknown>) ?? {};
    return {
      spill_id: fallback.spillId,
      source_scene_id: fallback.sourceSceneId,
      geometry: feature.geometry,
      oil_confidence: raw.oil_confidence,
      ...properties,
    };
  }

  // Case 3: bare geometry, or nothing usable — carry only what we know is real.
  return {
    spill_id: fallback.spillId,
    source_scene_id: fallback.sourceSceneId,
    geometry: geojson,
    oil_confidence: raw.oil_confidence,
  };
}
