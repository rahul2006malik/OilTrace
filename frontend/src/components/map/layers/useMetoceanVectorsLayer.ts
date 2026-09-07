import { useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import { SlickDetection } from '../../../types';
import { fetchMetoceanGrid } from '../../../api/oiltraceApi';

export function useMetoceanVectorsLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  detection: SlickDetection,
  playbackTimeHours: number,
  isVisible: boolean
) {
  // 1. Initial Setup of Layer Sources and Paints
  useEffect(() => {
    if (!map || !mapLoaded || !detection?.centroid) return;

    const lineSourceId = 'wind-vector-lines-source';
    const tipSourceId = 'wind-vector-tips-source';

    const cLon = detection.centroid[0];
    const cLat = detection.centroid[1];
    const initialPoints: any[] = [];
    for (let dLon = -3; dLon <= 3; dLon += 1) {
      for (let dLat = -2; dLat <= 2; dLat += 1) {
        initialPoints.push({
          lon: cLon + dLon,
          lat: cLat + dLat,
          bearing_deg: 270,
          speed_knots: 6.2,
        });
      }
    }

    const initialLines: any[] = [];
    const initialTips: any[] = [];

    initialPoints.forEach((p, idx) => {
      const rad = (p.bearing_deg * Math.PI) / 180;
      const len = Math.max(0.06, Math.min(0.24, p.speed_knots * 0.025));
      const base = [p.lon - len * 0.3 * Math.sin(rad), p.lat - len * 0.3 * Math.cos(rad)];
      const tip = [p.lon + len * 0.7 * Math.sin(rad), p.lat + len * 0.7 * Math.cos(rad)];

      initialLines.push({
        type: 'Feature',
        properties: { id: idx, speed: p.speed_knots },
        geometry: { type: 'LineString', coordinates: [base, tip] },
      });

      initialTips.push({
        type: 'Feature',
        properties: { id: idx, speed: p.speed_knots },
        geometry: { type: 'Point', coordinates: tip },
      });
    });

    if (!map.getSource(lineSourceId)) {
      map.addSource(lineSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: initialLines },
      });

      map.addSource(tipSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: initialTips },
      });

      map.addLayer({
        id: 'wind-vector-lines',
        type: 'line',
        source: lineSourceId,
        paint: {
          'line-color': '#38BDF8',
          'line-width': 1.5,
          'line-opacity': 0.75,
        },
      });

      map.addLayer({
        id: 'wind-vector-tips',
        type: 'circle',
        source: tipSourceId,
        paint: {
          'circle-radius': 2,
          'circle-color': '#38BDF8',
          'circle-opacity': 0.9,
        },
      });
    }

    // Toggle layer visibility
    ['wind-vector-lines', 'wind-vector-tips'].forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none');
      }
    });
  }, [map, mapLoaded, detection?.centroid, isVisible]);

  // 2. Quantized & Debounced Grid Fetching from Backend
  useEffect(() => {
    let isCancelled = false;
    if (!map || !mapLoaded || !detection?.centroid || !isVisible) return;

    const cLon = detection.centroid[0];
    const cLat = detection.centroid[1];
    const bbox: [number, number, number, number] = [cLon - 3.5, cLat - 2.5, cLon + 3.5, cLat + 2.5];

    const quantizedHours = Math.round(playbackTimeHours / 6.0) * 6.0;
    const detTimeMs = new Date(detection.detected_at).getTime();
    const queryTimeMs = detTimeMs + quantizedHours * 3600 * 1000;
    const queryTime = new Date(queryTimeMs).toISOString();

    const timer = setTimeout(() => {
      fetchMetoceanGrid(bbox, queryTime, 0.6)
        .then((gridData) => {
          if (isCancelled || !map) return;
          const rawVectors = gridData?.vectors || gridData?.points || [];
          if (!rawVectors.length) return;

          const lineFeatures: any[] = [];
          const tipFeatures: any[] = [];

          rawVectors.forEach((p: any, idx: number) => {
            const bearing = p.wind?.bearing_deg ?? p.current?.bearing_deg ?? p.wind_deg ?? p.curr_deg ?? p.rotation ?? 270;
            const speed = p.wind?.speed_knots ?? p.current?.speed_knots ?? p.wind_speed ?? p.curr_speed ?? p.speed ?? 5.0;
            const rad = (bearing * Math.PI) / 180;
            const len = Math.max(0.06, Math.min(0.24, speed * 0.025));

            const base = [p.lon - len * 0.3 * Math.sin(rad), p.lat - len * 0.3 * Math.cos(rad)];
            const tip = [p.lon + len * 0.7 * Math.sin(rad), p.lat + len * 0.7 * Math.cos(rad)];

            lineFeatures.push({
              type: 'Feature',
              properties: { id: idx, speed, bearing },
              geometry: { type: 'LineString', coordinates: [base, tip] },
            });

            tipFeatures.push({
              type: 'Feature',
              properties: { id: idx, speed, bearing },
              geometry: { type: 'Point', coordinates: tip },
            });
          });

          const lineSrc = map.getSource('wind-vector-lines-source') as maplibregl.GeoJSONSource | undefined;
          if (lineSrc) {
            lineSrc.setData({ type: 'FeatureCollection', features: lineFeatures });
          }
          const tipSrc = map.getSource('wind-vector-tips-source') as maplibregl.GeoJSONSource | undefined;
          if (tipSrc) {
            tipSrc.setData({ type: 'FeatureCollection', features: tipFeatures });
          }
        })
        .catch((err) => {
          console.warn('[TacticalMap] Failed to fetch metocean grid:', err);
        });
    }, 350);

    return () => {
      isCancelled = true;
      clearTimeout(timer);
    };
  }, [map, mapLoaded, detection?.centroid, detection?.detected_at, Math.round(playbackTimeHours / 6.0), isVisible]);
}
