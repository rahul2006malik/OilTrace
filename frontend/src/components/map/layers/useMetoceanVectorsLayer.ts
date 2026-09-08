import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { SlickDetection } from '../../../types';
import { fetchMetoceanGrid } from '../../../api/oiltraceApi';

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
  playbackTimeHours: number,
  isVisible: boolean
) {
  const popupRef = useRef<maplibregl.Popup | null>(null);

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
          'line-width': 2.2,
          'line-opacity': 0.85,
        },
      });
    }

    // Source 2: Surface Winds (ECMWF ERA5)
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
          'line-width': 1.6,
          'line-opacity': 0.75,
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
          'line-width': 2.6,
          'line-opacity': 0.90,
        },
      });
    }

    // Interactive Hover Telemetry Popup
    const handleVectorHover = (e: any) => {
      if (!e.features || e.features.length === 0) return;
      map.getCanvas().style.cursor = 'pointer';
      const props = e.features[0].properties || {};
      const coords = e.lngLat;

      if (!popupRef.current) {
        popupRef.current = new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 10,
        });
      }

      const html = `
        <div style="background:#0D1522; border:1px solid #1E2C3F; color:#E2E8F0; padding:8px 10px; font-family:monospace; font-size:11px; border-radius:3px; box-shadow:0 8px 24px rgba(0,0,0,0.7); min-width:200px;">
          <div style="font-weight:bold; color:#F1F5F9; font-size:11px; margin-bottom:4px; border-bottom:1px solid #1E2C3F; padding-bottom:3px;">
            METOCEAN VECTOR PROBE
          </div>
          <div style="display:flex; justify-content:space-between; margin-bottom:3px;">
            <span style="color:#2DD4BF;">🌊 CURRENT (GLORYS):</span>
            <span style="font-weight:bold; color:#FFFFFF;">${props.c_speed || '0.0'} kn @ ${props.c_bearing || '0'}°</span>
          </div>
          <div style="display:flex; justify-content:space-between; margin-bottom:3px;">
            <span style="color:#F59E0B;">💨 WIND (ERA5):</span>
            <span style="font-weight:bold; color:#FFFFFF;">${props.w_speed || '0.0'} kn @ ${props.w_bearing || '0'}°</span>
          </div>
          <div style="display:flex; justify-content:space-between; border-top:1px solid #1E2C3F; margin-top:4px; padding-top:3px;">
            <span style="color:#A855F7; font-weight:bold;">🎯 NET LEAP DRIFT:</span>
            <span style="font-weight:bold; color:#A855F7;">${props.net_speed || '0.0'} kn @ ${props.net_bearing || '0'}°</span>
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

  // 2. Hourly Responsive Grid Fetching from Backend Synchronized with Scrubber
  useEffect(() => {
    let isCancelled = false;
    if (!map || !mapLoaded || !detection?.centroid || !isVisible) return;

    const cLon = detection.centroid[0];
    const cLat = detection.centroid[1];
    const bbox: [number, number, number, number] = [cLon - 3.5, cLat - 2.5, cLon + 3.5, cLat + 2.5];

    // Hourly quantization for responsive temporal playback
    const quantizedHours = Math.round(playbackTimeHours / 1.0) * 1.0;
    const detTimeMs = new Date(detection.detected_at).getTime();
    const queryTimeMs = detTimeMs + quantizedHours * 3600 * 1000;
    const queryTime = new Date(queryTimeMs).toISOString();

    const timer = setTimeout(() => {
      fetchMetoceanGrid(bbox, queryTime, 0.6)
        .then((gridData) => {
          if (isCancelled || !map) return;
          const rawVectors = gridData?.vectors || gridData?.points || [];
          if (!rawVectors.length) return;

          const currentFeatures: any[] = [];
          const windFeatures: any[] = [];
          const netDriftFeatures: any[] = [];

          rawVectors.forEach((p: any, idx: number) => {
            const cSpeed = p.current?.speed_knots ?? 0.8;
            const cBearing = p.current?.bearing_deg ?? 180;

            const wSpeed = p.wind?.speed_knots ?? 10.0;
            const wBearing = p.wind?.bearing_deg ?? 45;

            const netSpeed = p.net_drift?.speed_knots ?? (cSpeed + 0.03 * wSpeed);
            const netBearing = p.net_drift?.bearing_deg ?? cBearing;

            const baseProps = {
              id: idx,
              c_speed: cSpeed.toFixed(1),
              c_bearing: cBearing.toFixed(0),
              w_speed: wSpeed.toFixed(1),
              w_bearing: wBearing.toFixed(0),
              net_speed: netSpeed.toFixed(1),
              net_bearing: netBearing.toFixed(0),
            };

            // Ocean Current vector (scale 0.08, len 0.06-0.22)
            const currentCoords = makeChevronVector(p.lon, p.lat, cBearing, cSpeed, 0.08, 0.06, 0.22);
            currentFeatures.push({
              type: 'Feature',
              properties: { ...baseProps, field: 'current' },
              geometry: { type: 'LineString', coordinates: currentCoords },
            });

            // Surface Wind vector (scale 0.015, len 0.07-0.26)
            const windCoords = makeChevronVector(p.lon, p.lat, wBearing, wSpeed, 0.015, 0.07, 0.26);
            windFeatures.push({
              type: 'Feature',
              properties: { ...baseProps, field: 'wind' },
              geometry: { type: 'LineString', coordinates: windCoords },
            });

            // Resultant Net Drift vector (scale 0.09, len 0.07-0.24)
            const netCoords = makeChevronVector(p.lon, p.lat, netBearing, netSpeed, 0.09, 0.07, 0.24);
            netDriftFeatures.push({
              type: 'Feature',
              properties: { ...baseProps, field: 'net_drift' },
              geometry: { type: 'LineString', coordinates: netCoords },
            });
          });

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
    }, 200);

    return () => {
      isCancelled = true;
      clearTimeout(timer);
    };
  }, [map, mapLoaded, detection?.centroid, detection?.detected_at, Math.round(playbackTimeHours / 1.0), isVisible]);
}
