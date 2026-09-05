/**
 * ConfessionFootprintLayer — Forward Dispersion Simulated Footprint (Layer 5).
 *
 * Active only when a candidate is selected AND has a matching entry in
 * `originConeData.forward_hypotheses[]`. Renders the candidate's forward
 * dispersion polygon with a dashed sky-blue outline and IoU overlap badge.
 *
 * Note: `forward_hypotheses` is currently [] in the cached origin_ensemble.json.
 * This layer will render nothing until the Drift subsystem produces forward
 * hypothesis footprints. This is correct behavior per the schema contract.
 */

import { useEffect, useMemo } from "react";
import { useMap } from "./mapContext";
import { useScenario } from "../../context/ScenarioContext";
import type { ForwardHypothesis } from "../../types/schemas";

const SOURCE_ID = "confession-source";
const FILL_LAYER_ID = "confession-fill";
const OUTLINE_LAYER_ID = "confession-outline";

export default function ConfessionFootprintLayer() {
  const map = useMap();
  const { originConeData, selectedCandidateId } = useScenario();

  // Find the forward hypothesis matching the selected candidate
  const hypothesis = useMemo<ForwardHypothesis | null>(() => {
    if (!selectedCandidateId || !originConeData?.forward_hypotheses?.length) {
      return null;
    }
    return (
      originConeData.forward_hypotheses.find(
        (h) => h.vessel_id === selectedCandidateId
      ) ?? null
    );
  }, [selectedCandidateId, originConeData]);

  useEffect(() => {
    if (!map) return;

    // If no hypothesis, remove existing layers and return
    if (!hypothesis) {
      try {
        if (map.getLayer(OUTLINE_LAYER_ID)) map.removeLayer(OUTLINE_LAYER_ID);
        if (map.getLayer(FILL_LAYER_ID)) map.removeLayer(FILL_LAYER_ID);
        if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
      } catch {
        /* safe cleanup */
      }
      return;
    }

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            iou: hypothesis.shape_overlap_score,
          },
          geometry: hypothesis.simulated_footprint,
        },
      ],
    };

    // Source
    if (!map.getSource(SOURCE_ID)) {
      map.addSource(SOURCE_ID, { type: "geojson", data: geojson });
    } else {
      (map.getSource(SOURCE_ID) as unknown as { setData: (d: GeoJSON.GeoJSON) => void }).setData(geojson);
    }

    // Fill layer
    if (!map.getLayer(FILL_LAYER_ID)) {
      map.addLayer({
        id: FILL_LAYER_ID,
        type: "fill",
        source: SOURCE_ID,
        paint: {
          "fill-color": "rgba(56, 189, 248, 0.15)",
        },
      });
    }

    // Outline layer — dashed
    if (!map.getLayer(OUTLINE_LAYER_ID)) {
      map.addLayer({
        id: OUTLINE_LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        paint: {
          "line-color": "rgba(56, 189, 248, 0.9)",
          "line-width": 1.5,
          "line-dasharray": [6, 4],
        },
      });
    }

    return () => {
      try {
        if (map.getLayer(OUTLINE_LAYER_ID)) map.removeLayer(OUTLINE_LAYER_ID);
        if (map.getLayer(FILL_LAYER_ID)) map.removeLayer(FILL_LAYER_ID);
        if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
      } catch {
        /* map may already be disposed */
      }
    };
  }, [map, hypothesis]);

  // Render IoU badge only when hypothesis is active
  if (!hypothesis) return null;

  const iouPercent = Math.round(hypothesis.shape_overlap_score * 100);

  return (
    <div className="absolute left-1/2 top-14 z-20 -translate-x-1/2 border border-chart-contour bg-chart-surface/95 px-3 py-1.5">
      <span className="font-mono text-[11px] tabular-nums text-prov-aisstream">
        IoU OVERLAP: {iouPercent}%
      </span>
    </div>
  );
}
