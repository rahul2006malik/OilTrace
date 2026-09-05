/**
 * OriginConeLayer — Origin Probability Cone (Layer 2).
 *
 * Renders the 50%/75%/90% KDE-derived probability contours from
 * `originConeData.origin_probability_cone`. Each polygon feature carries
 * `properties.probability` (0.5, 0.75, 0.9).
 *
 * Step styling:
 *   50% Core  → fill rgba(45,212,191,0.45), outline 1.5px solid #2DD4BF
 *   75% Mid   → fill rgba(45,212,191,0.22), outline 1px solid #2DD4BF
 *   90% Outer → fill rgba(45,212,191,0.08), outline 1px dashed rgba(45,212,191,0.5)
 */

import { useEffect } from "react";
import { useMap } from "./mapContext";
import { useScenario } from "../../context/ScenarioContext";

interface ConeConfig {
  suffix: string;
  maxProb: number;
  fillColor: string;
  lineColor: string;
  lineWidth: number;
  lineDash: number[] | undefined;
}

const TIERS: ConeConfig[] = [
  {
    suffix: "90",
    maxProb: 0.9,
    fillColor: "rgba(45, 212, 191, 0.08)",
    lineColor: "rgba(45, 212, 191, 0.5)",
    lineWidth: 1,
    lineDash: [4, 4],
  },
  {
    suffix: "75",
    maxProb: 0.75,
    fillColor: "rgba(45, 212, 191, 0.22)",
    lineColor: "#2DD4BF",
    lineWidth: 1,
    lineDash: undefined,
  },
  {
    suffix: "50",
    maxProb: 0.5,
    fillColor: "rgba(45, 212, 191, 0.45)",
    lineColor: "#2DD4BF",
    lineWidth: 1.5,
    lineDash: undefined,
  },
];

function sourceId(tier: ConeConfig) {
  return `cone-${tier.suffix}-source`;
}
function fillId(tier: ConeConfig) {
  return `cone-${tier.suffix}-fill`;
}
function lineId(tier: ConeConfig) {
  return `cone-${tier.suffix}-outline`;
}

export default function OriginConeLayer() {
  const map = useMap();
  const { originConeData } = useScenario();

  useEffect(() => {
    if (!map || !originConeData?.origin_probability_cone?.features?.length) {
      return;
    }

    const allFeatures = originConeData.origin_probability_cone.features;
    const layerIds: string[] = [];
    const sourceIds: string[] = [];

    for (const tier of TIERS) {
      const features = allFeatures.filter((f) => {
        const p = (f.properties as Record<string, unknown>)?.probability;
        return typeof p === "number" && p <= tier.maxProb && p > (tier.maxProb === 0.5 ? 0 : tier.maxProb === 0.75 ? 0.5 : 0.75);
      });

      // If no feature matches this exact tier, try using the feature that matches this probability level
      const tierFeatures = features.length > 0
        ? features
        : allFeatures.filter((f) => {
            const p = (f.properties as Record<string, unknown>)?.probability;
            return p === tier.maxProb;
          });

      if (tierFeatures.length === 0) continue;

      const geojson: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: tierFeatures,
      };

      const sid = sourceId(tier);
      const fid = fillId(tier);
      const lid = lineId(tier);

      sourceIds.push(sid);
      layerIds.push(fid, lid);

      // Source
      if (!map.getSource(sid)) {
        map.addSource(sid, { type: "geojson", data: geojson });
      } else {
        (map.getSource(sid) as unknown as { setData: (d: GeoJSON.GeoJSON) => void }).setData(geojson);
      }

      // Fill layer
      if (!map.getLayer(fid)) {
        map.addLayer({
          id: fid,
          type: "fill",
          source: sid,
          paint: {
            "fill-color": tier.fillColor,
          },
        });
      }

      // Outline layer
      if (!map.getLayer(lid)) {
        const layoutSpec: Record<string, unknown> = {};
        const paintSpec: Record<string, unknown> = {
          "line-color": tier.lineColor,
          "line-width": tier.lineWidth,
        };
        if (tier.lineDash) {
          paintSpec["line-dasharray"] = tier.lineDash;
        }
        map.addLayer({
          id: lid,
          type: "line",
          source: sid,
          layout: layoutSpec as maplibregl.LineLayerSpecification["layout"],
          paint: paintSpec as maplibregl.LineLayerSpecification["paint"],
        });
      }
    }

    return () => {
      try {
        for (const id of layerIds) {
          if (map.getLayer(id)) map.removeLayer(id);
        }
        for (const id of sourceIds) {
          if (map.getSource(id)) map.removeSource(id);
        }
      } catch {
        /* map may already be disposed */
      }
    };
  }, [map, originConeData]);

  return null;
}
