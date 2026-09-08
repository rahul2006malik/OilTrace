import { useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import { DriftRun, SlickDetection } from '../../../types';
import { useOilTraceStore } from '../../../store/useOilTraceStore';

export function useOriginConeLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  driftRun: DriftRun | null,
  detection: SlickDetection,
  isVisible: boolean
) {
  const playbackTimeHours = useOilTraceStore((s) => s.playbackTimeHours);
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
      // Advection Geodesic Link between Origin Hotspot and Satellite Slick Centroid
      const advectionSourceId = 'origin-advection-source';
      const dLatRad = ((detection.centroid[1] - hotspotCoords[1]) * Math.PI) / 180;
      const dLonRad = ((detection.centroid[0] - hotspotCoords[0]) * Math.PI) / 180;
      const havA =
        Math.sin(dLatRad / 2) * Math.sin(dLatRad / 2) +
        Math.cos((hotspotCoords[1] * Math.PI) / 180) *
          Math.cos((detection.centroid[1] * Math.PI) / 180) *
          Math.sin(dLonRad / 2) *
          Math.sin(dLonRad / 2);
      const distKm = 6371 * 2 * Math.atan2(Math.sqrt(havA), Math.sqrt(1 - havA));

      const bY = Math.sin(dLonRad) * Math.cos((detection.centroid[1] * Math.PI) / 180);
      const bX =
        Math.cos((hotspotCoords[1] * Math.PI) / 180) * Math.sin((detection.centroid[1] * Math.PI) / 180) -
        Math.sin((hotspotCoords[1] * Math.PI) / 180) *
          Math.cos((detection.centroid[1] * Math.PI) / 180) *
          Math.cos(dLonRad);
      const bearingDeg = Math.round(((Math.atan2(bY, bX) * 180) / Math.PI + 360) % 360);

      const midLon = (hotspotCoords[0] + detection.centroid[0]) / 2;
      const midLat = (hotspotCoords[1] + detection.centroid[1]) / 2;

      const advectionGeoJson: any = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: { role: 'link' },
            geometry: {
              type: 'LineString',
              coordinates: [hotspotCoords, detection.centroid],
            },
          },
          {
            type: 'Feature',
            properties: {
              role: 'label',
              text: `Advection Vector: ${distKm.toFixed(1)} km @ ${bearingDeg}° (GLORYS + ERA5)`,
            },
            geometry: {
              type: 'Point',
              coordinates: [midLon, midLat],
            },
          },
        ],
      };

      if (map.getSource(advectionSourceId)) {
        (map.getSource(advectionSourceId) as maplibregl.GeoJSONSource).setData(advectionGeoJson);
      } else {
        map.addSource(advectionSourceId, { type: 'geojson', data: advectionGeoJson });

        map.addLayer({
          id: 'origin-advection-line',
          type: 'line',
          source: advectionSourceId,
          filter: ['==', ['get', 'role'], 'link'],
          paint: {
            'line-color': '#F59E0B',
            'line-width': 2,
            'line-dasharray': [3, 2],
            'line-opacity': 0.85,
          },
        });

        map.addLayer({
          id: 'origin-advection-label',
          type: 'symbol',
          source: advectionSourceId,
          filter: ['==', ['get', 'role'], 'label'],
          layout: {
            'text-field': ['get', 'text'],
            'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
            'text-size': 10,
            'text-offset': [0, -1],
            'text-anchor': 'bottom',
          },
          paint: {
            'text-color': '#FDE68A',
            'text-halo-color': '#060B11',
            'text-halo-width': 2,
          },
        });
      }
    }

    // Toggle visibility
    const coneLayers = [
      'cone-fill',
      'cone-line',
      'origin-hotspot-core',
      'origin-hotspot-ring',
      'origin-advection-line',
      'origin-advection-label',
    ];
    coneLayers.forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none');
      }
    });
  }, [map, mapLoaded, driftRun, detection, isVisible]);

  // Dynamic origin KDE cone opacity with scrubber (preserves tiered 50/75/90% hierarchy)
  useEffect(() => {
    if (!map || !mapLoaded || !isVisible) return;

    let onsetDiff = 999;
    if (driftRun?.origin_zone?.estimated_onset_time && detection?.detected_at) {
      const onsetMs = new Date(driftRun.origin_zone.estimated_onset_time).getTime();
      const detMs = new Date(detection.detected_at).getTime();
      if (!isNaN(onsetMs) && !isNaN(detMs)) {
        const targetOnsetHours = (onsetMs - detMs) / (3600 * 1000);
        onsetDiff = Math.abs(playbackTimeHours - targetOnsetHours);
      }
    }
    const isAtOnset = onsetDiff <= 2.5;

    if (map.getLayer('origin-hotspot-ring')) {
      map.setPaintProperty('origin-hotspot-ring', 'circle-radius', isAtOnset ? 24 : 14);
      map.setPaintProperty('origin-hotspot-ring', 'circle-opacity', isAtOnset ? 0.45 : 0.20);
      map.setPaintProperty('origin-hotspot-ring', 'circle-stroke-width', isAtOnset ? 2.5 : 1.5);
      map.setPaintProperty('origin-hotspot-ring', 'circle-stroke-color', isAtOnset ? '#F59E0B' : '#EF4444');
    }

    if (map.getLayer('cone-line')) {
      map.setPaintProperty('cone-line', 'line-width', isAtOnset ? 2.8 : 1.8);
      map.setPaintProperty('cone-line', 'line-opacity', isAtOnset ? 1.0 : 0.75);
    }
  }, [map, mapLoaded, driftRun?.origin_zone?.estimated_onset_time, detection?.detected_at, playbackTimeHours, isVisible]);
}
