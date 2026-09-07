import { useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import { DriftRun } from '../../../types';

export function useStreamlinesLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  driftRun: DriftRun | null,
  playbackTimeHours: number,
  isVisible: boolean
) {
  // 1. Initial setup of streamline & particle head layers
  useEffect(() => {
    if (!map || !mapLoaded || !driftRun?.members?.length) return;

    const streamSourceId = 'streamlines-source';
    const headsSourceId = 'particle-heads-source';

    if (!map.getSource(streamSourceId)) {
      map.addSource(streamSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'streamlines-line',
        type: 'line',
        source: streamSourceId,
        paint: {
          'line-color': '#38BDF8',
          'line-width': 1.8,
          'line-opacity': 0.8,
        },
      });
    }

    if (!map.getSource(headsSourceId)) {
      map.addSource(headsSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'particle-heads-glow',
        type: 'circle',
        source: headsSourceId,
        paint: {
          'circle-radius': 5.5,
          'circle-color': '#38BDF8',
          'circle-opacity': 0.45,
        },
      });

      map.addLayer({
        id: 'particle-heads-core',
        type: 'circle',
        source: headsSourceId,
        paint: {
          'circle-radius': 2.5,
          'circle-color': '#FFFFFF',
          'circle-stroke-width': 1,
          'circle-stroke-color': '#0284c7',
        },
      });
    }

    // Toggle visibility
    ['streamlines-line', 'particle-heads-glow', 'particle-heads-core'].forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none');
      }
    });
  }, [map, mapLoaded, driftRun, isVisible]);

  // 2. High-performance Scrubber Animation (Animates particles and forward confession trails)
  useEffect(() => {
    if (!map || !mapLoaded || !driftRun?.members?.length || !isVisible) return;

    const streamSource = map.getSource('streamlines-source') as maplibregl.GeoJSONSource | undefined;
    const headsSource = map.getSource('particle-heads-source') as maplibregl.GeoJSONSource | undefined;
    if (!streamSource || !headsSource) return;

    // Normalization: -48.0h (origin) -> 0.0, 0.0h (detection horizon) -> 1.0
    const timeFraction = Math.max(0.0, Math.min(1.0, (playbackTimeHours + 48.0) / 48.0));

    const streamFeatures: any[] = [];
    const headFeatures: any[] = [];

    driftRun.members.forEach((m, idx) => {
      const fullCoords = m.backward_track.map((pt) => [pt.lon, pt.lat]);
      if (fullCoords.length < 2) return;

      // Position of the particle along the track at current time
      const exactIndex = (fullCoords.length - 1) * timeFraction;
      const lowIdx = Math.floor(exactIndex);
      const highIdx = Math.min(fullCoords.length - 1, lowIdx + 1);
      const subFrac = exactIndex - lowIdx;

      const currentLon = fullCoords[lowIdx][0] + (fullCoords[highIdx][0] - fullCoords[lowIdx][0]) * subFrac;
      const currentLat = fullCoords[lowIdx][1] + (fullCoords[highIdx][1] - fullCoords[lowIdx][1]) * subFrac;

      // Particle leading droplet head
      headFeatures.push({
        type: 'Feature',
        properties: { id: idx, isCore: true },
        geometry: { type: 'Point', coordinates: [currentLon, currentLat] },
      });

      // Forward Confession: plume dispersion
      if (timeFraction > 0.05) {
        const dispersionRadius = 0.007 * Math.sqrt(timeFraction);
        const angle1 = (idx * 1.37) % (Math.PI * 2);
        const angle2 = (idx * 2.89 + 1.2) % (Math.PI * 2);
        headFeatures.push({
          type: 'Feature',
          properties: { id: `${idx}-disp1`, isCore: false },
          geometry: {
            type: 'Point',
            coordinates: [
              currentLon + Math.cos(angle1) * dispersionRadius,
              currentLat + Math.sin(angle1) * dispersionRadius,
            ],
          },
        });
        headFeatures.push({
          type: 'Feature',
          properties: { id: `${idx}-disp2`, isCore: false },
          geometry: {
            type: 'Point',
            coordinates: [
              currentLon + Math.cos(angle2) * dispersionRadius * 0.7,
              currentLat + Math.sin(angle2) * dispersionRadius * 0.7,
            ],
          },
        });
      }

      // Forward confession trail
      const originPath = fullCoords.slice(0, lowIdx + 1);
      const trail = [...originPath, [currentLon, currentLat]];

      streamFeatures.push({
        type: 'Feature',
        properties: { member_id: m.member_id, windage: m.windage_coefficient },
        geometry: { type: 'LineString', coordinates: trail.length >= 2 ? trail : [trail[0], trail[0]] },
      });
    });

    streamSource.setData({
      type: 'FeatureCollection',
      features: streamFeatures,
    });

    headsSource.setData({
      type: 'FeatureCollection',
      features: headFeatures,
    });
  }, [map, mapLoaded, driftRun, playbackTimeHours, isVisible]);
}
