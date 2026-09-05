/**
 * ChartCanvas — Main WebGL tactical canvas wrapper.
 *
 * Initialises a MapLibre GL JS map with the Carto Dark Matter basemap,
 * desaturated to match the ECDIS --chart-abyss (#060B11) background.
 * Provides the map instance to child layer components via MapProvider,
 * renders the coordinate HUD, legend, and layer controls.
 */

import React, { useEffect, useRef, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { MapProvider } from "./mapContext";
import { useScenario } from "../../context/ScenarioContext";
import SlickLayer from "./SlickLayer";
import OriginConeLayer from "./OriginConeLayer";
import TrajectoryStreamlinesLayer from "./TrajectoryStreamlinesLayer";
import CandidateMarkersLayer from "./CandidateMarkersLayer";
import ConfessionFootprintLayer from "./ConfessionFootprintLayer";
import MapLegend from "./MapLegend";
import MapControls from "./MapControls";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BASEMAP_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

/** Default center: Arabian Sea operational area. */
const DEFAULT_CENTER: [number, number] = [64.8, 18.58];
const DEFAULT_ZOOM = 7;

// ---------------------------------------------------------------------------
// Coordinate display helpers
// ---------------------------------------------------------------------------

/**
 * Convert decimal degrees to nautical DMS string.
 * Output example: `18°34'12"N` or `064°42'55"E`.
 */
function decimalToDMS(decimal: number, isLat: boolean): string {
  const abs = Math.abs(decimal);
  const d = Math.floor(abs);
  const mFull = (abs - d) * 60;
  const m = Math.floor(mFull);
  const s = Math.round((mFull - m) * 60);
  const dir = isLat
    ? decimal >= 0
      ? "N"
      : "S"
    : decimal >= 0
      ? "E"
      : "W";
  const pad = isLat ? 2 : 3;
  return `${String(d).padStart(pad, "0")}°${String(m).padStart(2, "0")}'${String(s).padStart(2, "0")}"${dir}`;
}

/**
 * Compute the bounding box of a GeoJSON FeatureCollection by walking
 * all coordinate arrays. Returns a MapLibre LngLatBoundsLike pair
 * `[[minLon, minLat], [maxLon, maxLat]]`, or null if empty.
 */
function boundsFromFC(
  fc: GeoJSON.FeatureCollection
): [[number, number], [number, number]] | null {
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;

  function walk(coords: unknown): void {
    if (!Array.isArray(coords)) return;
    if (typeof coords[0] === "number" && typeof coords[1] === "number") {
      const [lon, lat] = coords as [number, number];
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    } else {
      for (const c of coords) walk(c);
    }
  }

  for (const f of fc.features) {
    if (f.geometry && "coordinates" in f.geometry) {
      walk((f.geometry as GeoJSON.Geometry & { coordinates: unknown }).coordinates);
    }
  }

  if (!isFinite(minLon)) return null;
  return [
    [minLon, minLat],
    [maxLon, maxLat],
  ];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChartCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapInstance, setMapInstance] = useState<maplibregl.Map | null>(null);
  const [cursorCoords, setCursorCoords] = useState("—");

  const {
    currentScenario,
    slickData,
    originConeData,
    attributionData,
    selectedCandidateId,
  } = useScenario();

  // ── Map initialisation ────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP_STYLE,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: false,
    });

    map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      "bottom-right"
    );

    map.on("load", () => {
      // Desaturate basemap background to chart-abyss
      try {
        if (map.getLayer("background")) {
          map.setPaintProperty("background", "background-color", "#060B11");
        }
      } catch {
        /* basemap may lack a named background layer */
      }
      setMapInstance(map);
    });

    map.on("mousemove", (e: maplibregl.MapMouseEvent) => {
      const { lng, lat } = e.lngLat;
      setCursorCoords(
        `${decimalToDMS(lat, true)}, ${decimalToDMS(lng, false)}`
      );
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      setMapInstance(null);
    };
  }, []);

  // ── Auto-fit bounds on data arrival ──────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapInstance) return;

    let minLon = Infinity;
    let minLat = Infinity;
    let maxLon = -Infinity;
    let maxLat = -Infinity;
    let hasPoints = false;

    // Expand by origin cone
    if (originConeData?.origin_probability_cone?.features?.length) {
      const coneBounds = boundsFromFC(originConeData.origin_probability_cone);
      if (coneBounds) {
        minLon = Math.min(minLon, coneBounds[0][0]);
        minLat = Math.min(minLat, coneBounds[0][1]);
        maxLon = Math.max(maxLon, coneBounds[1][0]);
        maxLat = Math.max(maxLat, coneBounds[1][1]);
        hasPoints = true;
      }
    }

    // Expand by slick
    if (slickData?.centroid) {
      minLon = Math.min(minLon, slickData.centroid[0]);
      minLat = Math.min(minLat, slickData.centroid[1]);
      maxLon = Math.max(maxLon, slickData.centroid[0]);
      maxLat = Math.max(maxLat, slickData.centroid[1]);
      hasPoints = true;
    }

    // Expand by candidates with coordinates
    const positionedCandidates = (attributionData?.candidates ?? []).filter(
      (c) => c.last_known_position != null
    );
    if (positionedCandidates.length > 0) {
      for (const c of positionedCandidates) {
        const [lon, lat] = c.last_known_position!;
        minLon = Math.min(minLon, lon);
        minLat = Math.min(minLat, lat);
        maxLon = Math.max(maxLon, lon);
        maxLat = Math.max(maxLat, lat);
      }
      hasPoints = true;
    }

    if (hasPoints && isFinite(minLon)) {
      map.fitBounds(
        [
          [minLon, minLat],
          [maxLon, maxLat],
        ],
        { padding: 70, duration: 1000 }
      );
      return;
    }

    // Fall back to the scenario's broad bounding box
    if (currentScenario?.bbox) {
      const [minLonB, minLatB, maxLonB, maxLatB] = currentScenario.bbox;
      map.fitBounds(
        [
          [minLonB, minLatB],
          [maxLonB, maxLatB],
        ],
        { padding: 60, duration: 1000 }
      );
    }
  }, [mapInstance, currentScenario, originConeData, slickData, attributionData]);

  // ── Fly camera on candidate selection ────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedCandidateId || !attributionData?.candidates) return;
    const cand = attributionData.candidates.find(
      (c) => c.vessel_id === selectedCandidateId
    );
    if (cand?.last_known_position) {
      map.flyTo({
        center: cand.last_known_position as [number, number],
        zoom: 9.5,
        duration: 800,
      });
    }
  }, [selectedCandidateId, attributionData]);

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <MapProvider value={mapInstance}>
      <div className="relative h-full w-full">
        {/* WebGL canvas mount point */}
        <div ref={containerRef} className="absolute inset-0" />

        {/* Forensic overlay layers — mount only after map ready */}
        {mapInstance && (
          <>
            <OriginConeLayer />
            <TrajectoryStreamlinesLayer />
            <SlickLayer />
            <ConfessionFootprintLayer />
            <CandidateMarkersLayer />
          </>
        )}

        {/* Coordinate HUD — bottom-right */}
        <div className="absolute bottom-3 right-3 z-10 border border-chart-contour bg-chart-surface/90 px-2 py-1">
          <span className="font-mono text-[11px] tabular-nums text-ink-secondary">
            {cursorCoords}
          </span>
        </div>

        {/* Chart legend — bottom-left */}
        <MapLegend />

        {/* Layer toggle controls — top-right */}
        {mapInstance && <MapControls />}
      </div>
    </MapProvider>
  );
}
