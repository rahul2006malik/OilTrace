import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { SlickDetection } from '../../../types';
import { fetchMetoceanGrid } from '../../../api/oiltraceApi';
import { useOilTraceStore } from '../../../store/useOilTraceStore';

function makeChevronVector(
  lon: number,
  lat: number,
  bearingDeg: number,
  speedKnots: number,
  scaleFactor: number,
  minLen: number,
  maxLen: number
): [number, number][] {
  const rad = (bearingDeg * Math.PI) / 180;
  const len = Math.max(minLen, Math.min(maxLen, speedKnots * scaleFactor));
  const base: [number, number] = [lon - len * 0.3 * Math.sin(rad), lat - len * 0.3 * Math.cos(rad)];
  const tip: [number, number] = [lon + len * 0.7 * Math.sin(rad), lat + len * 0.7 * Math.cos(rad)];

  // 145-degree arrow barbs
  const barbAngle = (145 * Math.PI) / 180;
  const barbLen = len * 0.35;
  const leftBarb: [number, number] = [
    tip[0] + barbLen * Math.sin(rad + barbAngle),
    tip[1] + barbLen * Math.cos(rad + barbAngle),
  ];
  const rightBarb: [number, number] = [
    tip[0] + barbLen * Math.sin(rad - barbAngle),
    tip[1] + barbLen * Math.cos(rad - barbAngle),
  ];

  return [base, tip, leftBarb, tip, rightBarb];
}

export function useMetoceanVectorsLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  detection: SlickDetection,
  isVisible: boolean
) {
  const playbackTimeHours = useOilTraceStore((s) => s.playbackTimeHours);
  const activeScenarioId = useOilTraceStore((s) => s.activeScenarioId);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const gridCacheRef = useRef<Map<string, { currentFeatures: any[]; windFeatures: any[]; netDriftFeatures: any[] }>>(new Map());

  // 1. Initialize MapLibre GeoJSON Sources & Vector Layers
  useEffect(() => {
    if (!map || !mapLoaded || !detection?.centroid) return;

    const currentSourceId = 'metocean-currents-source';
    const windSourceId = 'metocean-winds-source';
    const netDriftSourceId = 'metocean-net-drift-source';

    // Source 1: Ocean Surface Currents (Copernicus GLORYS)
    if (!map.getSource(currentSourceId)) {
      map.addSource(currentSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });
      map.addLayer({
        id: 'metocean-currents-layer',
        type: 'line',
        source: currentSourceId,
        paint: {
          'line-color': '#2DD4BF', // Neon Teal
          'line-width': 2.4,
          'line-opacity': 0.90,
        },
      });
    }

    // Source 2: Surface Winds (ECMWF ERA5 10m)
    if (!map.getSource(windSourceId)) {
      map.addSource(windSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });
      map.addLayer({
        id: 'metocean-winds-layer',
        type: 'line',
        source: windSourceId,
        paint: {
          'line-color': '#F59E0B', // Amber
          'line-width': 1.8,
          'line-opacity': 0.80,
          'line-dasharray': [4, 2],
        },
      });
    }

    // Source 3: Resultant Net Oil Drift Vectors (Current + 3% Windage)
    if (!map.getSource(netDriftSourceId)) {
      map.addSource(netDriftSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });
      map.addLayer({
        id: 'metocean-net-drift-layer',
        type: 'line',
        source: netDriftSourceId,
        paint: {
          'line-color': '#A855F7', // Purple
          'line-width': 3.0,
          'line-opacity': 0.95,
        },
      });
    }

    // Interactive Hover Telemetry Popup with Color Identification & Physics Deconstruction
    const handleVectorHover = (e: any) => {
      if (!e.features || e.features.length === 0) return;
      map.getCanvas().style.cursor = 'pointer';
      const props = e.features[0].properties || {};
      const hoveredField = props.field || 'net_drift';
      const coords = e.lngLat;

      if (!popupRef.current) {
        popupRef.current = new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 12,
        });
      }

      // Physics decomposition: Current is 100% advection, Wind is 3% leeway
      const cSpeedNum = parseFloat(props.c_speed) || 0.0;
      const wSpeedNum = parseFloat(props.w_speed) || 0.0;
      const wLeewaySpeed = wSpeedNum * 0.03;
      const totalDrivingPower = cSpeedNum + wLeewaySpeed;
      const currentPct = totalDrivingPower > 0.01 ? Math.max(10, Math.min(95, Math.round((cSpeedNum / totalDrivingPower) * 100))) : 75;
      const windPct = 100 - currentPct;

      let fieldBadge = '';
      let fieldDesc = '';

      if (hoveredField === 'current') {
        fieldBadge = `
          <div style="display:inline-flex; align-items:center; gap:6px; background:#0F766E2E; border:1px solid #2DD4BF; color:#2DD4BF; padding:3px 8px; border-radius:3px; font-weight:bold; font-size:10px; letter-spacing:0.5px;">
            <span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:#2DD4BF; box-shadow:0 0 6px #2DD4BF;"></span>
            TEAL ARROW: OCEAN SURFACE CURRENT
          </div>`;
        fieldDesc = `
          <div style="font-size:9.5px; color:#94A3B8; margin-top:5px; line-height:1.4;">
            Primary advection force: Directly moves surface layer with <strong style="color:#2DD4BF;">100% velocity transfer</strong> to the slick (Copernicus GLORYS12V1).
          </div>`;
      } else if (hoveredField === 'wind') {
        fieldBadge = `
          <div style="display:inline-flex; align-items:center; gap:6px; background:#B453092E; border:1px solid #F59E0B; color:#F59E0B; padding:3px 8px; border-radius:3px; font-weight:bold; font-size:10px; letter-spacing:0.5px;">
            <span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:#F59E0B; box-shadow:0 0 6px #F59E0B;"></span>
            AMBER ARROW: SURFACE WIND (10m)
          </div>`;
        fieldDesc = `
          <div style="font-size:9.5px; color:#94A3B8; margin-top:5px; line-height:1.4;">
            Atmospheric windage: Oil slick absorbs only <strong style="color:#F59E0B;">3.0% leeway drift speed</strong> (ECMWF ERA5; 97% passes overhead).
          </div>`;
      } else {
        fieldBadge = `
          <div style="display:inline-flex; align-items:center; gap:6px; background:#7E22CE2E; border:1px solid #A855F7; color:#A855F7; padding:3px 8px; border-radius:3px; font-weight:bold; font-size:10px; letter-spacing:0.5px;">
            <span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:#A855F7; box-shadow:0 0 6px #A855F7;"></span>
            PURPLE ARROW: RESULTANT NET OIL DRIFT
          </div>`;
        fieldDesc = `
          <div style="font-size:9.5px; color:#94A3B8; margin-top:5px; line-height:1.4;">
            Combined physical drift vector driving slick: <code style="color:#E2E8F0; background:#1E2C3F; padding:1px 4px; border-radius:2px;">V⃗_drift = V⃗_curr + 0.03·V⃗_wind</code>.
          </div>`;
      }

      const html = `
        <div style="background:#0D1522; border:1px solid #1E2C3F; color:#E2E8F0; padding:10px 12px; font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size:11px; border-radius:4px; box-shadow:0 12px 30px rgba(0,0,0,0.85); min-width:250px; max-width:300px;">
          <!-- Active Arrow Identifier Header -->
          <div style="margin-bottom:6px;">
            ${fieldBadge}
            ${fieldDesc}
          </div>

          <!-- Divider -->
          <div style="height:1px; background:#1E2C3F; margin:8px 0;"></div>

          <!-- Metocean Telemetry Rows -->
          <div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:10.5px;">
            <span style="color:#2DD4BF;">🌊 Current (100%):</span>
            <span style="font-weight:bold; color:#F1F5F9;">${props.c_speed || '0.0'} kn @ ${props.c_bearing || '0'}°</span>
          </div>
          <div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:10.5px;">
            <span style="color:#F59E0B;">💨 Wind Leeway (3%):</span>
            <span style="font-weight:bold; color:#F1F5F9;">+${wLeewaySpeed.toFixed(2)} kn <span style="color:#64748B; font-size:9px;">(${props.w_speed} kn @ ${props.w_bearing}°)</span></span>
          </div>
          <div style="display:flex; justify-content:space-between; border-top:1px dashed #1E2C3F; margin-top:5px; padding-top:5px; font-size:11px;">
            <span style="color:#A855F7; font-weight:bold;">🎯 Net Slick Drift:</span>
            <span style="font-weight:bold; color:#A855F7;">${props.net_speed || '0.0'} kn @ ${props.net_bearing || '0'}°</span>
          </div>

          <!-- Momentum Power Influence Bar -->
          <div style="margin-top:8px; padding-top:6px; border-top:1px solid #1E2C3F;">
            <div style="display:flex; justify-content:space-between; font-size:9px; color:#94A3B8; margin-bottom:3px;">
              <span>DRIFT POWER SHARE:</span>
              <span>
                <strong style="color:#2DD4BF;">${currentPct}% Curr</strong> / <strong style="color:#F59E0B;">${windPct}% Wind</strong>
              </span>
            </div>
            <div style="display:flex; height:5px; border-radius:3px; overflow:hidden; background:#1E2C3F;">
              <div style="width:${currentPct}%; background:#2DD4BF;" title="Current: ${currentPct}%"></div>
              <div style="width:${windPct}%; background:#F59E0B;" title="Wind Leeway: ${windPct}%"></div>
            </div>
          </div>
        </div>
      `;

      popupRef.current.setLngLat(coords).setHTML(html).addTo(map);
    };

    const handleVectorLeave = () => {
      map.getCanvas().style.cursor = '';
      if (popupRef.current) {
        popupRef.current.remove();
      }
    };

    map.on('mousemove', 'metocean-currents-layer', handleVectorHover);
    map.on('mouseleave', 'metocean-currents-layer', handleVectorLeave);
    map.on('mousemove', 'metocean-winds-layer', handleVectorHover);
    map.on('mouseleave', 'metocean-winds-layer', handleVectorLeave);
    map.on('mousemove', 'metocean-net-drift-layer', handleVectorHover);
    map.on('mouseleave', 'metocean-net-drift-layer', handleVectorLeave);

    // Toggle layer visibility
    ['metocean-currents-layer', 'metocean-winds-layer', 'metocean-net-drift-layer'].forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none');
      }
    });

    return () => {
      map.off('mousemove', 'metocean-currents-layer', handleVectorHover);
      map.off('mouseleave', 'metocean-currents-layer', handleVectorLeave);
      map.off('mousemove', 'metocean-winds-layer', handleVectorHover);
      map.off('mouseleave', 'metocean-winds-layer', handleVectorLeave);
      map.off('mousemove', 'metocean-net-drift-layer', handleVectorHover);
      map.off('mouseleave', 'metocean-net-drift-layer', handleVectorLeave);
      if (popupRef.current) {
        popupRef.current.remove();
      }
    };
  }, [map, mapLoaded, detection?.centroid, isVisible]);

  // Clear cache if detection/centroid or active scenario changes
  useEffect(() => {
    gridCacheRef.current.clear();
  }, [detection?.centroid?.[0], detection?.centroid?.[1], detection?.detected_at, activeScenarioId]);

  // 2. Hourly Responsive Grid Fetching with In-Memory Cache Synchronized with Scrubber
  useEffect(() => {
    let isCancelled = false;
    if (!map || !mapLoaded || !detection?.centroid || !isVisible) return;

    const cLon = detection.centroid[0];
    const cLat = detection.centroid[1];
    const bbox: [number, number, number, number] = [cLon - 3.5, cLat - 2.5, cLon + 3.5, cLat + 2.5];

    // Hourly quantization for responsive temporal playback
    const quantizedHours = Math.round(playbackTimeHours / 1.0) * 1.0;
    const cacheKey = `${activeScenarioId || 'default'}_${quantizedHours}`;

    // Fast Path: Immediate cache hit (Zero network delay, zero UI lag)
    if (gridCacheRef.current.has(cacheKey)) {
      const cached = gridCacheRef.current.get(cacheKey)!;
      const curSrc = map.getSource('metocean-currents-source') as maplibregl.GeoJSONSource | undefined;
      if (curSrc) curSrc.setData({ type: 'FeatureCollection', features: cached.currentFeatures });

      const windSrc = map.getSource('metocean-winds-source') as maplibregl.GeoJSONSource | undefined;
      if (windSrc) windSrc.setData({ type: 'FeatureCollection', features: cached.windFeatures });

      const netSrc = map.getSource('metocean-net-drift-source') as maplibregl.GeoJSONSource | undefined;
      if (netSrc) netSrc.setData({ type: 'FeatureCollection', features: cached.netDriftFeatures });
      return;
    }

    const detTimeMs = new Date(detection.detected_at).getTime();
    const queryTimeMs = detTimeMs + quantizedHours * 3600 * 1000;
    const queryTime = new Date(queryTimeMs).toISOString();

    // Debounce network requests during active dragging so we never flood the backend
    const timer = setTimeout(() => {
      fetchMetoceanGrid(bbox, queryTime, 0.6, activeScenarioId)
        .then((gridData) => {
          if (isCancelled || !map) return;
          const rawVectors = gridData?.vectors || gridData?.points || [];
          if (!rawVectors.length) return;

          const currentFeatures: any[] = [];
          const windFeatures: any[] = [];
          const netDriftFeatures: any[] = [];

          rawVectors.forEach((p: any, idx: number) => {
            const cSpeed = p.current?.speed_knots ?? p.curr_speed ?? 0.8;
            const cBearing = p.current?.bearing_deg ?? p.curr_deg ?? 180;

            const wSpeed = p.wind?.speed_knots ?? p.wind_speed ?? 10.0;
            const wBearing = p.wind?.bearing_deg ?? p.wind_deg ?? 45;

            const netSpeed = p.net_drift?.speed_knots ?? (cSpeed + 0.03 * wSpeed);
            const netBearing = p.net_drift?.bearing_deg ?? cBearing;

            const baseProps = {
              id: idx,
              c_speed: Number(cSpeed).toFixed(1),
              c_bearing: Number(cBearing).toFixed(0),
              w_speed: Number(wSpeed).toFixed(1),
              w_bearing: Number(wBearing).toFixed(0),
              net_speed: Number(netSpeed).toFixed(1),
              net_bearing: Number(netBearing).toFixed(0),
            };

            // Ocean Current vector (scale 0.14, len 0.025-0.28)
            // Directly reflects ocean current speed (0.2 to 2.0 knots)
            const currentCoords = makeChevronVector(p.lon, p.lat, cBearing, cSpeed, 0.14, 0.025, 0.28);
            currentFeatures.push({
              type: 'Feature',
              properties: { ...baseProps, field: 'current' },
              geometry: { type: 'LineString', coordinates: currentCoords },
            });

            // Surface Wind vector (scale 0.009, len 0.035-0.24)
            // Visual atmospheric flow (5 to 30 knots) without visually overshadowing current
            const windCoords = makeChevronVector(p.lon, p.lat, wBearing, wSpeed, 0.009, 0.035, 0.24);
            windFeatures.push({
              type: 'Feature',
              properties: { ...baseProps, field: 'wind' },
              geometry: { type: 'LineString', coordinates: windCoords },
            });

            // Resultant Net Drift vector (scale 0.15, len 0.030-0.30)
            // Magnitude of net slick drift speed
            const netCoords = makeChevronVector(p.lon, p.lat, netBearing, netSpeed, 0.15, 0.030, 0.30);
            netDriftFeatures.push({
              type: 'Feature',
              properties: { ...baseProps, field: 'net_drift' },
              geometry: { type: 'LineString', coordinates: netCoords },
            });
          });

          // Store in in-memory cache
          gridCacheRef.current.set(cacheKey, { currentFeatures, windFeatures, netDriftFeatures });

          const curSrc = map.getSource('metocean-currents-source') as maplibregl.GeoJSONSource | undefined;
          if (curSrc) {
            curSrc.setData({ type: 'FeatureCollection', features: currentFeatures });
          }

          const windSrc = map.getSource('metocean-winds-source') as maplibregl.GeoJSONSource | undefined;
          if (windSrc) {
            windSrc.setData({ type: 'FeatureCollection', features: windFeatures });
          }

          const netSrc = map.getSource('metocean-net-drift-source') as maplibregl.GeoJSONSource | undefined;
          if (netSrc) {
            netSrc.setData({ type: 'FeatureCollection', features: netDriftFeatures });
          }
        })
        .catch((err) => {
          console.warn('[TacticalMap] Failed to fetch metocean grid:', err);
        });
    }, 800);

    return () => {
      isCancelled = true;
      clearTimeout(timer);
    };
  }, [
    map,
    mapLoaded,
    detection?.centroid?.[0],
    detection?.centroid?.[1],
    detection?.detected_at,
    activeScenarioId,
    Math.round(playbackTimeHours / 1.0),
    isVisible,
  ]);
}
