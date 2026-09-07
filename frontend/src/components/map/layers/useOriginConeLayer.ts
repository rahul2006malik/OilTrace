import { useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import { DriftRun, SlickDetection } from '../../../types';

export function useOriginConeLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  driftRun: DriftRun | null,
  detection: SlickDetection,
  playbackTimeHours: number,
  isVisible: boolean
) {
  useEffect(() => {
    if (!map || !mapLoaded) return;

    const coneSourceId = 'cone-source';
    const originHotspotSourceId = 'origin-hotspot-source';

    if (driftRun && driftRun.origin_zone) {
      const coneFeatures: any[] = [
        {
          type: 'Feature',
          properties: { level: '90% Contour (Outer)', color: '#4F46E5', opacity: 0.18 },
          geometry: driftRun.origin_zone.p90,
        },
        {
          type: 'Feature',
          properties: { level: '75% Contour (Mid)', color: '#818CF8', opacity: 0.28 },
          geometry: driftRun.origin_zone.p75,
        },
        {
          type: 'Feature',
          properties: { level: '50% Core Origin Zone', color: '#EF4444', opacity: 0.45 },
          geometry: driftRun.origin_zone.p50,
        },
      ];

      const coneGeoJson: any = { type: 'FeatureCollection', features: coneFeatures };

      if (map.getSource(coneSourceId)) {
        (map.getSource(coneSourceId) as maplibregl.GeoJSONSource).setData(coneGeoJson);
      } else {
        map.addSource(coneSourceId, { type: 'geojson', data: coneGeoJson });

        map.addLayer({
          id: 'cone-fill',
          type: 'fill',
          source: coneSourceId,
          paint: {
            'fill-color': ['get', 'color'],
            'fill-opacity': ['get', 'opacity'],
          },
        });

        map.addLayer({
          id: 'cone-line',
          type: 'line',
          source: coneSourceId,
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 2,
            'line-dasharray': [3, 2],
          },
        });
      }

      // Bayesian hotspot centroid
      const p50Ring = (driftRun.origin_zone.p50 as any)?.coordinates?.[0];
      let hotspotCoords: [number, number];
      if (p50Ring && p50Ring.length > 1) {
        const cx = p50Ring.reduce((s: number, p: number[]) => s + p[0], 0) / p50Ring.length;
        const cy = p50Ring.reduce((s: number, p: number[]) => s + p[1], 0) / p50Ring.length;
        hotspotCoords = [cx, cy];
      } else {
        hotspotCoords = [detection.centroid[0] - 0.25, detection.centroid[1] - 0.15];
      }

      const hotspotGeoJson: any = {
        type: 'Feature',
        properties: { name: 'Probable Discharge Origin (68% Bayesian Hotspot)' },
        geometry: { type: 'Point', coordinates: hotspotCoords },
      };

      if (map.getSource(originHotspotSourceId)) {
        (map.getSource(originHotspotSourceId) as maplibregl.GeoJSONSource).setData(hotspotGeoJson);
      } else {
        map.addSource(originHotspotSourceId, { type: 'geojson', data: hotspotGeoJson });

        map.addLayer({
          id: 'origin-hotspot-ring',
          type: 'circle',
          source: originHotspotSourceId,
          paint: {
            'circle-radius': 16,
            'circle-color': '#EF4444',
            'circle-opacity': 0.25,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#EF4444',
          },
        });

        map.addLayer({
          id: 'origin-hotspot-core',
          type: 'circle',
          source: originHotspotSourceId,
          paint: {
            'circle-radius': 5,
            'circle-color': '#EF4444',
            'circle-stroke-width': 2,
            'circle-stroke-color': '#FFFFFF',
          },
        });
      }
    }

    // Toggle visibility
    const coneLayers = ['cone-fill', 'cone-line', 'origin-hotspot-core', 'origin-hotspot-ring'];
    coneLayers.forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none');
      }
    });

    // Dynamic origin KDE cone opacity with scrubber
    if (map.getLayer('cone-fill') && isVisible) {
      const rewindProgress = Math.min(1.0, Math.max(0.0, -playbackTimeHours / 48.0));
      const dynamicOpacity = 0.08 + rewindProgress * 0.37;
      map.setPaintProperty('cone-fill', 'fill-opacity', dynamicOpacity);
    }
  }, [map, mapLoaded, driftRun, detection, playbackTimeHours, isVisible]);
}
