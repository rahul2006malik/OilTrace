/**
 * CandidateMarkersLayer — Candidate Vessel Markers (Layer 4).
 *
 * Plots attribution candidates at their `last_known_position` as MapLibre
 * circle markers. Size scales smoothly by suspicion_score (fallback to
 * anomaly_score). Border color is driven by data_provenance:
 *   real_gfw          → #2DD4BF (teal)
 *   real_aisstream_live → #38BDF8 (blue)
 *   synthetic_fallback → #927B56 (brass)
 *
 * Click: selects candidate and flies camera to position.
 */

import { useEffect, useMemo, useCallback } from "react";
import maplibregl from "maplibre-gl";
import { useMap } from "./mapContext";
import { useScenario } from "../../context/ScenarioContext";
import type { Candidate } from "../../types/schemas";

const SOURCE_ID = "candidates-source";
const BASE_LAYER_ID = "candidate-markers";
const SELECTED_LAYER_ID = "candidate-markers-selected";

const PROV_COLORS: Record<string, string> = {
  real_gfw: "#2DD4BF",
  real_aisstream_live: "#38BDF8",
  synthetic_fallback: "#927B56",
};

function getScore(c: Candidate): number {
  if (c.suspicion_score != null && isFinite(c.suspicion_score)) {
    return c.suspicion_score;
  }
  return c.evidence_trace?.anomaly_score ?? 0.5;
}

function candidatesToGeoJSON(
  candidates: Candidate[]
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: candidates
      .filter((c) => c.last_known_position != null)
      .map((c) => ({
        type: "Feature" as const,
        properties: {
          vessel_id: c.vessel_id,
          vessel_name: c.vessel_name ?? c.vessel_id,
          score: getScore(c),
          provenance: c.data_provenance,
          provColor: PROV_COLORS[c.data_provenance] ?? "#927B56",
        },
        geometry: {
          type: "Point" as const,
          coordinates: c.last_known_position as [number, number],
        },
      })),
  };
}

export default function CandidateMarkersLayer() {
  const map = useMap();
  const { attributionData, selectedCandidateId, setSelectedCandidateId } =
    useScenario();

  const candidates = attributionData?.candidates ?? [];

  const geojson = useMemo(
    () => candidatesToGeoJSON(candidates),
    [candidates]
  );

  // ── Add source & layers ──────────────────────────────────────────────
  useEffect(() => {
    if (!map || geojson.features.length === 0) return;

    // Source
    if (!map.getSource(SOURCE_ID)) {
      map.addSource(SOURCE_ID, { type: "geojson", data: geojson });
    } else {
      (map.getSource(SOURCE_ID) as unknown as { setData: (d: GeoJSON.GeoJSON) => void }).setData(geojson);
    }

    // Base marker layer
    if (!map.getLayer(BASE_LAYER_ID)) {
      map.addLayer({
        id: BASE_LAYER_ID,
        type: "circle",
        source: SOURCE_ID,
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["get", "score"],
            0,
            6,
            1,
            12,
          ],
          "circle-color": [
            "match",
            ["get", "provenance"],
            "real_gfw",
            "rgba(45, 212, 191, 0.20)",
            "real_aisstream_live",
            "rgba(56, 189, 248, 0.20)",
            "synthetic_fallback",
            "rgba(146, 123, 86, 0.20)",
            "rgba(146, 123, 86, 0.20)",
          ],
          "circle-stroke-color": ["get", "provColor"],
          "circle-stroke-width": 2,
        },
      });
    }

    // Selected highlight layer — initially shows nothing
    if (!map.getLayer(SELECTED_LAYER_ID)) {
      map.addLayer({
        id: SELECTED_LAYER_ID,
        type: "circle",
        source: SOURCE_ID,
        filter: ["==", ["get", "vessel_id"], ""],
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["get", "score"],
            0,
            10,
            1,
            16,
          ],
          "circle-color": "transparent",
          "circle-stroke-color": ["get", "provColor"],
          "circle-stroke-width": 3,
        },
      });
    }

    // Click handler
    const onClick = (
      e: maplibregl.MapMouseEvent & {
        features?: maplibregl.MapGeoJSONFeature[];
      }
    ) => {
      const feature = e.features?.[0];
      if (!feature) return;

      const vesselId = feature.properties?.vessel_id as string;
      if (!vesselId) return;

      setSelectedCandidateId(vesselId);

      const coords = (feature.geometry as GeoJSON.Point).coordinates as [
        number,
        number,
      ];
      map.flyTo({ center: coords, zoom: 9, duration: 800 });
    };

    map.on("click", BASE_LAYER_ID, onClick);

    // Hover cursor
    const onEnter = () => {
      map.getCanvas().style.cursor = "pointer";
    };
    const onLeave = () => {
      map.getCanvas().style.cursor = "";
    };
    map.on("mouseenter", BASE_LAYER_ID, onEnter);
    map.on("mouseleave", BASE_LAYER_ID, onLeave);

    return () => {
      try {
        map.off("click", BASE_LAYER_ID, onClick);
        map.off("mouseenter", BASE_LAYER_ID, onEnter);
        map.off("mouseleave", BASE_LAYER_ID, onLeave);
        if (map.getLayer(SELECTED_LAYER_ID)) map.removeLayer(SELECTED_LAYER_ID);
        if (map.getLayer(BASE_LAYER_ID)) map.removeLayer(BASE_LAYER_ID);
        if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
      } catch {
        /* map may already be disposed */
      }
    };
  }, [map, geojson, setSelectedCandidateId]);

  // ── Update selected highlight filter ─────────────────────────────────
  useEffect(() => {
    if (!map || !map.getLayer(SELECTED_LAYER_ID)) return;

    map.setFilter(SELECTED_LAYER_ID, [
      "==",
      ["get", "vessel_id"],
      selectedCandidateId ?? "",
    ]);
  }, [map, selectedCandidateId]);

  return null;
}
