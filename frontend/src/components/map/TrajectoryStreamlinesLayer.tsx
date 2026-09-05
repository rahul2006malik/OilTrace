/**
 * TrajectoryStreamlinesLayer — Hydrodynamic Hindcast Particle Streamlines (Layer 3).
 *
 * Converts the `trajectoriesData` array of 25 OpenDrift ensemble members
 * (each with parallel `lons[]` and `lats[]` arrays) into GeoJSON LineStrings
 * and renders them as thin sky-blue traces showing the real ocean current +
 * wind drift pathways from the Runge-Kutta 4th-order backward integration.
 *
 * Style: rgba(56, 189, 248, 0.35), 1.2px, round caps.
 */

import { useEffect, useMemo } from "react";
import { useMap } from "./mapContext";
import { useScenario } from "../../context/ScenarioContext";
import type { TrajectoryMember } from "../../types/schemas";

const SOURCE_ID = "trajectories-source";
const LAYER_ID = "trajectories-lines";

/**
 * Convert a TrajectoryMember (parallel lon/lat arrays) into a GeoJSON
 * LineString Feature by zipping lons[i] and lats[i] into [lon, lat] pairs.
 */
function memberToFeature(m: TrajectoryMember): GeoJSON.Feature<GeoJSON.LineString> {
  const len = Math.min(m.lons.length, m.lats.length);
  const coordinates: [number, number][] = [];
  for (let i = 0; i < len; i++) {
    coordinates.push([m.lons[i], m.lats[i]]);
  }
  return {
    type: "Feature",
    properties: { member: m.member },
    geometry: { type: "LineString", coordinates },
  };
}

export default function TrajectoryStreamlinesLayer() {
  const map = useMap();
  const { trajectoriesData } = useScenario();

  // Memoize the GeoJSON conversion — runs only when trajectory data changes
  const geojson = useMemo<GeoJSON.FeatureCollection>(() => {
    if (!trajectoriesData?.length) {
      return { type: "FeatureCollection", features: [] };
    }
    return {
      type: "FeatureCollection",
      features: trajectoriesData.map(memberToFeature),
    };
  }, [trajectoriesData]);

  useEffect(() => {
    if (!map || geojson.features.length === 0) return;

    // Source
    if (!map.getSource(SOURCE_ID)) {
      map.addSource(SOURCE_ID, { type: "geojson", data: geojson });
    } else {
      (map.getSource(SOURCE_ID) as unknown as { setData: (d: GeoJSON.GeoJSON) => void }).setData(geojson);
    }

    // Layer
    if (!map.getLayer(LAYER_ID)) {
      map.addLayer({
        id: LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        paint: {
          "line-color": "rgba(56, 189, 248, 0.35)",
          "line-width": 1.2,
        },
        layout: {
          "line-cap": "round",
          "line-join": "round",
        },
      });
    }

    return () => {
      try {
        if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
        if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
      } catch {
        /* map may already be disposed */
      }
    };
  }, [map, geojson]);

  return null;
}
