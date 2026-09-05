/**
 * SlickLayer — Observed SAR Slick Polygon (Layer 1).
 *
 * Renders the detected oil slick boundary from `slickData.geometry`.
 * Styling: teal (#2DD4BF) outline at 2px, fill at 15% opacity.
 * This is the ground-truth observed slick from Sentinel-1 SAR radiometry.
 */

import { useEffect } from "react";
import { useMap } from "./mapContext";
import { useScenario } from "../../context/ScenarioContext";

const SOURCE_ID = "slick-source";
const FILL_LAYER_ID = "slick-fill";
const OUTLINE_LAYER_ID = "slick-outline";

export default function SlickLayer() {
  const map = useMap();
  const { slickData } = useScenario();

  useEffect(() => {
    if (!map || !slickData?.geometry) return;

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {},
          geometry: slickData.geometry,
        },
      ],
    };

    // Add or update source
    if (!map.getSource(SOURCE_ID)) {
      map.addSource(SOURCE_ID, { type: "geojson", data: geojson });
    } else {
      (map.getSource(SOURCE_ID) as unknown as { setData: (d: GeoJSON.GeoJSON) => void }).setData(geojson);
    }

    // Add layers if not present
    if (!map.getLayer(FILL_LAYER_ID)) {
      map.addLayer({
        id: FILL_LAYER_ID,
        type: "fill",
        source: SOURCE_ID,
        paint: {
          "fill-color": "#2DD4BF",
          "fill-opacity": 0.15,
        },
      });
    }

    if (!map.getLayer(OUTLINE_LAYER_ID)) {
      map.addLayer({
        id: OUTLINE_LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        paint: {
          "line-color": "#2DD4BF",
          "line-width": 2,
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
  }, [map, slickData]);

  return null;
}
