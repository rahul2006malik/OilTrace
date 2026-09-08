import { useEffect, useMemo } from 'react';
import maplibregl from 'maplibre-gl';
import { DriftRun } from '../../../types';
import { useOilTraceStore } from '../../../store/useOilTraceStore';

export function useStreamlinesLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  driftRun: DriftRun | null,
  isVisible: boolean
) {
  const playbackTimeHours = useOilTraceStore((s) => s.playbackTimeHours);

  // 1. Static Setup: Full Ensemble Dispersion Fan, Lagrangian Ribbon, and Layers
  useEffect(() => {
    if (!map || !mapLoaded || !driftRun?.members?.length) return;

    const fanSourceId = 'ensemble-fan-source';
    const ribbonSourceId = 'advection-ribbon-source';
    const streamSourceId = 'streamlines-source';
    const headsSourceId = 'particle-heads-source';
    const beaconSourceId = 'discharge-beacon-source';

    // A. Full Stochastic Ensemble Fan (All 25 member trajectories showing complete dispersion corridor)
    const fanFeatures: any[] = [];
    const ribbonCoords: [number, number][] = [];
    const medianIdx = Math.floor(driftRun.members.length / 2);

    driftRun.members.forEach((m, idx) => {
      const fullCoords = m.backward_track.map((pt) => [pt.lon, pt.lat] as [number, number]);
      if (fullCoords.length < 2) return;

      fanFeatures.push({
        type: 'Feature',
        properties: { member_id: m.member_id, windage: m.windage_coefficient },
        geometry: { type: 'LineString', coordinates: fullCoords },
      });

      if (idx === medianIdx) {
        ribbonCoords.push(...fullCoords);
      }
    });

    if (!map.getSource(fanSourceId)) {
      map.addSource(fanSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: fanFeatures },
      });

      map.addLayer({
        id: 'ensemble-fan-lines',
        type: 'line',
        source: fanSourceId,
        paint: {
          'line-color': '#0284C7',
          'line-width': 1.2,
          'line-opacity': 0.22,
          'line-dasharray': [3, 2],
        },
      });
    } else {
      (map.getSource(fanSourceId) as maplibregl.GeoJSONSource).setData({
        type: 'FeatureCollection',
        features: fanFeatures,
      });
    }

    // B. Central Lagrangian Advection Ribbon (Dominant Hydrodynamic Current Streamline)
    const ribbonGeoJson = {
      type: 'FeatureCollection' as const,
      features: ribbonCoords.length >= 2 ? [
        {
          type: 'Feature' as const,
          properties: { label: 'Lagrangian Hydrodynamic Advection Streamline' },
          geometry: { type: 'LineString' as const, coordinates: ribbonCoords },
        },
      ] : [],
    };

    if (!map.getSource(ribbonSourceId)) {
      map.addSource(ribbonSourceId, {
        type: 'geojson',
        data: ribbonGeoJson,
      });

      map.addLayer({
        id: 'advection-ribbon-glow',
        type: 'line',
        source: ribbonSourceId,
        paint: {
          'line-color': '#06B6D4',
          'line-width': 5.0,
          'line-opacity': 0.35,
          'line-blur': 2.5,
        },
      });

      map.addLayer({
        id: 'advection-ribbon-line',
        type: 'line',
        source: ribbonSourceId,
        paint: {
          'line-color': '#38BDF8',
          'line-width': 2.2,
          'line-dasharray': [4, 2],
          'line-opacity': 0.85,
        },
      });
    } else {
      (map.getSource(ribbonSourceId) as maplibregl.GeoJSONSource).setData(ribbonGeoJson);
    }

    // C. Dynamic Active Streamlines (Illuminated trails up to current time)
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
          'line-color': '#2DD4BF',
          'line-width': 1.8,
          'line-opacity': 0.85,
        },
      });
    }

    // D. Dynamic Droplet Heads (Glowing particles with turbulent dispersion)
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
          'circle-radius': 7,
          'circle-color': '#2DD4BF',
          'circle-opacity': 0.45,
        },
      });

      map.addLayer({
        id: 'particle-heads-core',
        type: 'circle',
        source: headsSourceId,
        paint: {
          'circle-radius': 3.2,
          'circle-color': '#FFFFFF',
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#0F766E',
        },
      });
    }

    // E. Discharge Origin Beacon (Pulsing release beacon at estimated onset position)
    const originPoint = ribbonCoords.length > 0 ? ribbonCoords[0] : [0, 0];
    if (!map.getSource(beaconSourceId)) {
      map.addSource(beaconSourceId, {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: { label: 'Discharge Origin' },
              geometry: { type: 'Point', coordinates: originPoint },
            },
          ],
        },
      });

      map.addLayer({
        id: 'discharge-beacon-ping',
        type: 'circle',
        source: beaconSourceId,
        paint: {
          'circle-radius': 18,
          'circle-color': '#F59E0B',
          'circle-opacity': 0.35,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#F59E0B',
        },
      });

      map.addLayer({
        id: 'discharge-beacon-core',
        type: 'circle',
        source: beaconSourceId,
        paint: {
          'circle-radius': 4.5,
          'circle-color': '#FFFFFF',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#F59E0B',
        },
      });
    } else {
      (map.getSource(beaconSourceId) as maplibregl.GeoJSONSource).setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: { label: 'Discharge Origin' },
            geometry: { type: 'Point', coordinates: originPoint },
          },
        ],
      });
    }

    // Toggle visibility
    [
      'ensemble-fan-lines',
      'advection-ribbon-glow',
      'advection-ribbon-line',
      'streamlines-line',
      'particle-heads-glow',
      'particle-heads-core',
      'discharge-beacon-ping',
      'discharge-beacon-core',
    ].forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none');
      }
    });
  }, [map, mapLoaded, driftRun, isVisible]);

  // Memoize forward-chronological tracks for all ensemble members once per driftRun
  const cachedMemberTracks = useMemo(() => {
    if (!driftRun?.members?.length) return [];
    return driftRun.members
      .map((m) => {
        const rawCoords = m.backward_track.map((pt) => [pt.lon, pt.lat] as [number, number]);
        if (rawCoords.length < 2) return null;
        return {
          member_id: m.member_id,
          windage_coefficient: m.windage_coefficient,
          fullCoords: rawCoords,
        };
      })
      .filter(Boolean) as { member_id: number | string; windage_coefficient: number; fullCoords: [number, number][] }[];
  }, [driftRun]);

  // 2. High-performance Scrubber Animation (Physical chronological forward advection: Origin -> Slick)
  useEffect(() => {
    if (!map || !mapLoaded || !cachedMemberTracks.length || !isVisible) return;

    const streamSource = map.getSource('streamlines-source') as maplibregl.GeoJSONSource | undefined;
    const headsSource = map.getSource('particle-heads-source') as maplibregl.GeoJSONSource | undefined;
    if (!streamSource || !headsSource) return;

    // Calculate dynamic simulation window from forcing or trajectory timestamps
    let simWindowHours = 48.0;
    if (driftRun?.forcing?.window_start && driftRun?.forcing?.window_end) {
      const startMs = new Date(driftRun.forcing.window_start).getTime();
      const endMs = new Date(driftRun.forcing.window_end).getTime();
      if (!isNaN(startMs) && !isNaN(endMs) && endMs > startMs) {
        simWindowHours = Math.max(6.0, (endMs - startMs) / (3600 * 1000));
      }
    } else {
      const firstTrack = driftRun?.members?.[0]?.backward_track;
      if (firstTrack && firstTrack.length >= 2) {
        const t0 = new Date(firstTrack[0].t).getTime();
        const tEnd = new Date(firstTrack[firstTrack.length - 1].t).getTime();
        if (!isNaN(t0) && !isNaN(tEnd) && tEnd > t0) {
          simWindowHours = Math.max(6.0, (tEnd - t0) / (3600 * 1000));
        }
      }
    }

    // Normalization: -simWindowHours (origin/onset) -> 0.0, 0.0h (satellite detection horizon) -> 1.0
    const timeFraction = Math.max(0.0, Math.min(1.0, (playbackTimeHours + simWindowHours) / simWindowHours));

    const streamFeatures: any[] = [];
    const headFeatures: any[] = [];

    cachedMemberTracks.forEach((m, idx) => {
      const fullCoords = m.fullCoords;

      // Exact position of the advecting droplet along the track at current playback time
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

      // Spatio-temporal turbulent plume dispersion expanding from release point toward detection horizon
      if (timeFraction > 0.04) {
        const dispersionRadius = 0.0085 * Math.sqrt(timeFraction);
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
              currentLon + Math.cos(angle2) * dispersionRadius * 0.75,
              currentLat + Math.sin(angle2) * dispersionRadius * 0.75,
            ],
          },
        });
      }

      // Advection trail from origin up to current scrubbed position
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

    // Pulse the discharge origin beacon when near onset window
    if (map.getLayer('discharge-beacon-ping')) {
      const nearOnset = playbackTimeHours <= -(simWindowHours * 0.35) && playbackTimeHours >= -simWindowHours;
      const onsetProximity = Math.max(0.1, 1.0 - Math.abs(playbackTimeHours + simWindowHours * 0.5) / (simWindowHours * 0.5));
      map.setPaintProperty('discharge-beacon-ping', 'circle-radius', nearOnset ? 14 + onsetProximity * 12 : 10);
      map.setPaintProperty('discharge-beacon-ping', 'circle-opacity', nearOnset ? 0.2 + onsetProximity * 0.35 : 0.1);
    }
  }, [map, mapLoaded, cachedMemberTracks, playbackTimeHours, isVisible, driftRun]);
}
