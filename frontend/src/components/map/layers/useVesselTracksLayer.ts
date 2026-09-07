import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import { AttributionResult, SlickDetection } from '../../../types';

function getVesselPositionAtTime(
  positions: { timestamp: string; lon: number; lat: number }[] | undefined,
  targetTimeMs: number,
  fallback: [number, number]
): [number, number] {
  if (!positions || positions.length === 0) return fallback;
  if (positions.length === 1) return [positions[0].lon, positions[0].lat];

  const parsed = positions
    .map((p) => ({ lon: p.lon, lat: p.lat, timeMs: new Date(p.timestamp).getTime() }))
    .filter((p) => !isNaN(p.timeMs))
    .sort((a, b) => a.timeMs - b.timeMs);

  if (parsed.length === 0) return fallback;

  if (targetTimeMs <= parsed[0].timeMs) {
    return [parsed[0].lon, parsed[0].lat];
  }
  if (targetTimeMs >= parsed[parsed.length - 1].timeMs) {
    return [parsed[parsed.length - 1].lon, parsed[parsed.length - 1].lat];
  }

  for (let i = 0; i < parsed.length - 1; i++) {
    const p1 = parsed[i];
    const p2 = parsed[i + 1];
    if (targetTimeMs >= p1.timeMs && targetTimeMs <= p2.timeMs) {
      const span = p2.timeMs - p1.timeMs;
      const ratio = span > 0 ? (targetTimeMs - p1.timeMs) / span : 0;
      return [
        p1.lon + ratio * (p2.lon - p1.lon),
        p1.lat + ratio * (p2.lat - p1.lat),
      ];
    }
  }

  return fallback;
}

export function useVesselTracksLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  attribution: AttributionResult | null,
  detection: SlickDetection,
  selectedCandidateId: string | null,
  selectCandidate: (vesselId: string) => void,
  playbackTimeHours: number,
  isVesselsVisible: boolean,
  isRoutesVisible: boolean
) {
  const popupRef = useRef<maplibregl.Popup | null>(null);

  // 1. Static Routes, Discharge Gaps & Waypoints
  useEffect(() => {
    if (!map || !mapLoaded || !attribution?.candidates?.length) return;

    const routeSourceId = 'vessel-route-source';
    const dischargeSourceId = 'vessel-discharge-source';
    const waypointsSourceId = 'vessel-waypoints-source';

    const routeFeatures: any[] = [];
    const dischargeFeatures: any[] = [];
    const waypointFeatures: any[] = [];

    attribution.candidates.forEach((cand, cIdx) => {
      if (!cand.ais_positions || cand.ais_positions.length < 2) return;
      const isSelected = cand.vessel_id === (selectedCandidateId || attribution.candidates[0]?.vessel_id);
      const routeColor = isSelected ? '#F59E0B' : cIdx === 0 ? '#EF4444' : cIdx === 1 ? '#38BDF8' : cIdx === 2 ? '#A855F7' : '#64748B';
      const routeWidth = isSelected ? 3.5 : cIdx === 0 ? 2.5 : 1.5;
      const routeOpacity = isSelected ? 0.95 : cIdx <= 2 ? 0.65 : 0.35;

      routeFeatures.push({
        type: 'Feature',
        properties: {
          vessel_id: cand.vessel_id,
          name: cand.vessel_name || cand.vessel_id,
          color: routeColor,
          width: routeWidth,
          opacity: routeOpacity,
          isSelected,
        },
        geometry: {
          type: 'LineString',
          coordinates: cand.ais_positions.map((p: any) => [p.lon, p.lat]),
        },
      });

      let currentDischargeRun: number[][] = [];
      for (let i = 0; i < cand.ais_positions.length; i++) {
        const pt = cand.ais_positions[i];
        const isGapOrReconstructed = Boolean(pt.is_reconstructed);

        if (isGapOrReconstructed) {
          if (currentDischargeRun.length === 0 && i > 0) {
            currentDischargeRun.push([cand.ais_positions[i - 1].lon, cand.ais_positions[i - 1].lat]);
          }
          currentDischargeRun.push([pt.lon, pt.lat]);
        } else {
          if (currentDischargeRun.length > 0) {
            currentDischargeRun.push([pt.lon, pt.lat]);
            if (currentDischargeRun.length >= 2) {
              dischargeFeatures.push({
                type: 'Feature',
                properties: {
                  vessel_id: cand.vessel_id,
                  vessel_name: cand.vessel_name,
                  is_gap: true,
                },
                geometry: {
                  type: 'LineString',
                  coordinates: [...currentDischargeRun],
                },
              });
            }
            currentDischargeRun = [];
          }
        }
      }
      if (currentDischargeRun.length >= 2) {
        dischargeFeatures.push({
          type: 'Feature',
          properties: {
            vessel_id: cand.vessel_id,
            vessel_name: cand.vessel_name,
            is_gap: true,
          },
          geometry: {
            type: 'LineString',
            coordinates: currentDischargeRun,
          },
        });
      }

      if (isSelected) {
        cand.ais_positions.forEach((p: any, idx: number) => {
          waypointFeatures.push({
            type: 'Feature',
            properties: {
              timestamp: p.timestamp,
              sog: p.sog,
              cog: p.cog,
              idx,
              isDischarge: Boolean(p.is_reconstructed),
            },
            geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
          });
        });
      }
    });

    const routeGeoJson: any = { type: 'FeatureCollection', features: routeFeatures };
    const dischargeGeoJson: any = { type: 'FeatureCollection', features: dischargeFeatures };
    const waypointsGeoJson: any = { type: 'FeatureCollection', features: waypointFeatures };

    if (map.getSource(routeSourceId)) {
      (map.getSource(routeSourceId) as maplibregl.GeoJSONSource).setData(routeGeoJson);
    } else {
      map.addSource(routeSourceId, { type: 'geojson', data: routeGeoJson });
      map.addLayer({
        id: 'vessel-route-line',
        type: 'line',
        source: routeSourceId,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['get', 'width'],
          'line-opacity': ['get', 'opacity'],
          'line-dasharray': [4, 2],
        },
      });
    }

    if (map.getSource(dischargeSourceId)) {
      (map.getSource(dischargeSourceId) as maplibregl.GeoJSONSource).setData(dischargeGeoJson);
    } else {
      map.addSource(dischargeSourceId, { type: 'geojson', data: dischargeGeoJson });
      map.addLayer({
        id: 'vessel-discharge-segments',
        type: 'line',
        source: dischargeSourceId,
        paint: {
          'line-color': '#EF4444',
          'line-width': 4.5,
          'line-dasharray': [2, 1],
          'line-opacity': 0.95,
        },
      });
    }

    if (map.getSource(waypointsSourceId)) {
      (map.getSource(waypointsSourceId) as maplibregl.GeoJSONSource).setData(waypointsGeoJson);
    } else {
      map.addSource(waypointsSourceId, { type: 'geojson', data: waypointsGeoJson });
      map.addLayer({
        id: 'vessel-route-waypoints',
        type: 'circle',
        source: waypointsSourceId,
        paint: {
          'circle-radius': 3.5,
          'circle-color': ['case', ['get', 'isDischarge'], '#EF4444', '#F59E0B'],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#060B11',
        },
      });
    }

    // Toggle route layers
    ['vessel-route-line', 'vessel-discharge-segments', 'vessel-route-waypoints'].forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isRoutesVisible ? 'visible' : 'none');
      }
    });
  }, [map, mapLoaded, attribution, selectedCandidateId, isRoutesVisible]);

  // 2. Initial Setup of Vessel Marker Layers and Interaction Handlers
  useEffect(() => {
    if (!map || !mapLoaded || !attribution?.candidates?.length) return;

    const vesselSourceId = 'vessels-source';
    const headingSourceId = 'vessel-heading-source';

    if (!map.getSource(vesselSourceId)) {
      map.addSource(vesselSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      // Outer halo
      map.addLayer({
        id: 'vessel-points-glow',
        type: 'circle',
        source: vesselSourceId,
        paint: {
          'circle-radius': ['case', ['get', 'isSelected'], 16, 10],
          'circle-color': ['get', 'color'],
          'circle-opacity': ['case', ['get', 'isSelected'], 0.35, 0.15],
        },
      });

      // Core marker
      map.addLayer({
        id: 'vessel-points',
        type: 'circle',
        source: vesselSourceId,
        paint: {
          'circle-radius': ['case', ['get', 'isSelected'], 8, 6],
          'circle-color': ['get', 'color'],
          'circle-stroke-width': 2,
          'circle-stroke-color': '#FFFFFF',
        },
      });

      // Label
      map.addLayer({
        id: 'vessel-labels',
        type: 'symbol',
        source: vesselSourceId,
        layout: {
          'text-field': ['get', 'vessel_name'],
          'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
          'text-size': 10,
          'text-offset': [0, 1.4],
          'text-anchor': 'top',
        },
        paint: {
          'text-color': '#FFFFFF',
          'text-halo-color': '#060B11',
          'text-halo-width': 1.5,
        },
      });

      // Vessel click
      map.on('click', 'vessel-points', (e) => {
        if (e.features && e.features.length > 0) {
          const vid = e.features[0].properties?.vessel_id;
          if (vid) {
            if (popupRef.current) {
              popupRef.current.remove();
            }
            selectCandidate(vid);
          }
        }
      });

      // Vessel hover
      map.on('mousemove', 'vessel-points', (e) => {
        if (!e.features || e.features.length === 0) return;
        map.getCanvas().style.cursor = 'pointer';
        const f = e.features[0];
        const props = f.properties || {};
        const coords = (f.geometry as any).coordinates.slice();

        if (!popupRef.current) {
          popupRef.current = new maplibregl.Popup({
            closeButton: false,
            closeOnClick: false,
            offset: 14,
          });
        }

        const html = `
          <div style="background:#0D1522; border:1px solid #1E2C3F; color:#E2E8F0; padding:8px 10px; font-family:monospace; font-size:11px; border-radius:3px; box-shadow:0 8px 24px rgba(0,0,0,0.6); min-width:180px;">
            <div style="font-weight:bold; color:#38BDF8; font-size:12px; margin-bottom:4px;">${props.vessel_name || props.vessel_id}</div>
            <div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span style="color:#64748B;">MMSI:</span><span>${props.vessel_id}</span></div>
            <div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span style="color:#64748B;">TYPE:</span><span>${props.type || 'Tanker'}</span></div>
            <div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span style="color:#64748B;">SPEED/COG:</span><span>${props.sog || 'N/A'} / ${props.cog || 'N/A'}</span></div>
            <div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span style="color:#64748B;">RISK:</span><span style="color:${props.isSelected ? '#2DD4BF' : '#EF4444'}; font-weight:bold;">${props.score}</span></div>
            <div style="display:flex; justify-content:space-between;"><span style="color:#64748B;">SRC:</span><span style="color:#94A3B8;">${props.provenance || 'real_gfw'}</span></div>
          </div>
        `;

        popupRef.current.setLngLat(coords).setHTML(html).addTo(map);
      });

      map.on('mouseleave', 'vessel-points', () => {
        map.getCanvas().style.cursor = '';
        if (popupRef.current) {
          popupRef.current.remove();
        }
      });
    }

    if (!map.getSource(headingSourceId)) {
      map.addSource(headingSourceId, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      map.addLayer({
        id: 'vessel-heading-vectors',
        type: 'line',
        source: headingSourceId,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['case', ['get', 'isSelected'], 2.5, 1.5],
          'line-dasharray': [2, 1],
          'line-opacity': 0.85,
        },
      });
    }

    // Toggle vessel layers
    ['vessel-points-glow', 'vessel-points', 'vessel-heading-vectors', 'vessel-labels'].forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isVesselsVisible ? 'visible' : 'none');
      }
    });
  }, [map, mapLoaded, attribution, selectCandidate, isVesselsVisible]);

  // 3. Animate Candidate Vessels along 4D tracks with Scrubber
  useEffect(() => {
    if (!map || !mapLoaded || !attribution?.candidates?.length || !isVesselsVisible) return;

    const vesselSource = map.getSource('vessels-source') as maplibregl.GeoJSONSource | undefined;
    const headingSource = map.getSource('vessel-heading-source') as maplibregl.GeoJSONSource | undefined;
    if (!vesselSource || !headingSource) return;

    const detTimeMs = new Date(detection.detected_at).getTime();
    const currentScrubberTimeMs = detTimeMs + playbackTimeHours * 3600 * 1000;

    const updatedVesselFeatures: any[] = [];
    const updatedHeadingFeatures: any[] = [];

    const sortedCandidates = [...attribution.candidates]
      .filter((c) => c.last_known_position)
      .sort((a, b) => {
        const isSelA = a.vessel_id === (selectedCandidateId || attribution.candidates[0]?.vessel_id);
        const isSelB = b.vessel_id === (selectedCandidateId || attribution.candidates[0]?.vessel_id);
        if (isSelA) return 1;
        if (isSelB) return -1;
        return (a.suspicion_score || 0) - (b.suspicion_score || 0);
      });

    sortedCandidates.forEach((c) => {
      const isSelected = c.vessel_id === (selectedCandidateId || attribution.candidates[0]?.vessel_id);
      const score = c.suspicion_score || 0;
      const markerColor = isSelected ? '#2DD4BF' : score > 0.65 ? '#EF4444' : score > 0.4 ? '#F59E0B' : '#64748B';
      const fallbackPos = c.last_known_position as [number, number];
      const currentPos = getVesselPositionAtTime(c.ais_positions, currentScrubberTimeMs, fallbackPos);

      const lastPos = c.ais_positions?.[c.ais_positions.length - 1];
      const sog = (c as any).sog ?? lastPos?.sog ?? 12.0;
      const rawCog = (c as any).cog ?? lastPos?.cog ?? 45.0;
      const isInvalidCog = rawCog >= 360 || rawCog === 511;
      const isStationary = sog < 0.8;

      updatedVesselFeatures.push({
        type: 'Feature' as const,
        properties: {
          vessel_id: c.vessel_id,
          vessel_name: c.vessel_name || `MMSI: ${c.vessel_id}`,
          type: c.vessel_type || 'Tanker',
          score: `${(score * 100).toFixed(1)}%`,
          sog: `${sog.toFixed(1)} kn`,
          cog: isInvalidCog ? 'N/A' : `${rawCog.toFixed(0)}°`,
          provenance: c.data_provenance,
          isSelected,
          color: markerColor,
        },
        geometry: {
          type: 'Point' as const,
          coordinates: currentPos,
        },
      });

      if (!isInvalidCog && !isStationary) {
        const headingRad = (rawCog * Math.PI) / 180;
        const vecLen = Math.max(0.08, Math.min(0.24, (sog / 20) * 0.18));
        const tipLon = currentPos[0] + vecLen * Math.sin(headingRad);
        const tipLat = currentPos[1] + vecLen * Math.cos(headingRad);

        updatedHeadingFeatures.push({
          type: 'Feature' as const,
          properties: {
            vessel_id: c.vessel_id,
            color: markerColor,
            isSelected,
          },
          geometry: {
            type: 'LineString' as const,
            coordinates: [currentPos, [tipLon, tipLat]],
          },
        });
      }
    });

    vesselSource.setData({
      type: 'FeatureCollection',
      features: updatedVesselFeatures,
    });

    headingSource.setData({
      type: 'FeatureCollection',
      features: updatedHeadingFeatures,
    });
  }, [map, mapLoaded, attribution, selectedCandidateId, playbackTimeHours, isVesselsVisible, detection.detected_at]);
}
