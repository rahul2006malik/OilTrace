/**
 * MapControls — Layer toggle pills and reset view (top-right).
 *
 * Compact control panel letting analysts toggle visibility of individual
 * forensic overlay layers and reset the camera to the incident bounding box.
 * No decorative effects — purely functional tactical instrument controls.
 */

import { useState, useCallback } from "react";
import { useMap } from "./mapContext";
import { useScenario } from "../../context/ScenarioContext";

// Well-known layer IDs matching those created by layer components
const STREAMLINE_LAYERS = ["trajectories-lines"];
const CONE_LAYERS = [
  "cone-90-fill",
  "cone-90-outline",
  "cone-75-fill",
  "cone-75-outline",
  "cone-50-fill",
  "cone-50-outline",
];
const MARKER_LAYERS = ["candidate-markers", "candidate-markers-selected"];

export default function MapControls() {
  const map = useMap();
  const { currentScenario } = useScenario();

  const [showStreamlines, setShowStreamlines] = useState(true);
  const [showCones, setShowCones] = useState(true);
  const [showMarkers, setShowMarkers] = useState(true);

  const setLayerVisibility = useCallback(
    (layerIds: string[], visible: boolean) => {
      if (!map) return;
      const vis = visible ? "visible" : "none";
      for (const id of layerIds) {
        try {
          if (map.getLayer(id)) {
            map.setLayoutProperty(id, "visibility", vis);
          }
        } catch {
          /* layer may not exist yet */
        }
      }
    },
    [map]
  );

  const handleResetView = useCallback(() => {
    if (!map) return;
    if (currentScenario?.bbox) {
      const [minLon, minLat, maxLon, maxLat] = currentScenario.bbox;
      map.fitBounds(
        [
          [minLon, minLat],
          [maxLon, maxLat],
        ],
        { padding: 60, duration: 800 }
      );
    }
  }, [map, currentScenario]);

  const handleToggleStreamlines = useCallback(() => {
    const next = !showStreamlines;
    setShowStreamlines(next);
    setLayerVisibility(STREAMLINE_LAYERS, next);
  }, [showStreamlines, setLayerVisibility]);

  const handleToggleCones = useCallback(() => {
    const next = !showCones;
    setShowCones(next);
    setLayerVisibility(CONE_LAYERS, next);
  }, [showCones, setLayerVisibility]);

  const handleToggleMarkers = useCallback(() => {
    const next = !showMarkers;
    setShowMarkers(next);
    setLayerVisibility(MARKER_LAYERS, next);
  }, [showMarkers, setLayerVisibility]);

  return (
    <div className="absolute right-3 top-3 z-10 flex flex-col gap-1.5 border border-chart-contour bg-chart-surface/95 p-2">
      <ControlPill label="RESET VIEW" active={false} onClick={handleResetView} />
      <div className="border-t border-chart-contour" />
      <ControlPill
        label="STREAMLINES"
        active={showStreamlines}
        onClick={handleToggleStreamlines}
      />
      <ControlPill
        label="CONES"
        active={showCones}
        onClick={handleToggleCones}
      />
      <ControlPill
        label="MARKERS"
        active={showMarkers}
        onClick={handleToggleMarkers}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component
// ---------------------------------------------------------------------------

function ControlPill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2.5 py-1 text-left font-sans text-[10px] uppercase tracking-wider transition-colors ${
        active
          ? "border border-prov-gfw/40 bg-chart-accent text-ink-primary"
          : "border border-chart-contour bg-chart-raised text-ink-secondary hover:bg-chart-hover hover:text-ink-primary"
      }`}
    >
      {label}
    </button>
  );
}
