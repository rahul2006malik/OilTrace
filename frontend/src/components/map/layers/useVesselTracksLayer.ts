import { useEffect, useRef, useMemo } from 'react';
import maplibregl from 'maplibre-gl';
import { AttributionResult, SlickDetection } from '../../../types';
import { useOilTraceStore } from '../../../store/useOilTraceStore';

function catmullRom1D(p0: number, p1: number, p2: number, p3: number, t: number): number {
  const t2 = t * t;
  const t3 = t2 * t;
  return 0.5 * (
    (2 * p1) +
    (-p0 + p2) * t +
    (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
    (-p0 + 3 * p1 - 3 * p2 + p3) * t3
  );
}

function buildCorridorPolygon(coords: number[][], widthDeg: number = 0.075): number[][][] {
  if (coords.length < 2) return [];
  const leftSide: number[][] = [];
  const rightSide: number[][] = [];

  for (let i = 0; i < coords.length; i++) {
    const prev = coords[Math.max(0, i - 1)];
    const next = coords[Math.min(coords.length - 1, i + 1)];
    const dx = next[0] - prev[0];
    const dy = next[1] - prev[1];
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;

    leftSide.push([coords[i][0] + nx * widthDeg, coords[i][1] + ny * widthDeg]);
    rightSide.push([coords[i][0] - nx * widthDeg, coords[i][1] - ny * widthDeg]);
  }

  return [[...leftSide, ...rightSide.reverse(), leftSide[0]]];
}

export interface InterpolatedVesselFix {
  lon: number;
  lat: number;
  sog: number;
  cog: number;
  is_reconstructed: boolean;
}

function getVesselPositionAtTime(
  positions: { timestamp: string; lon: number; lat: number; sog?: number; cog?: number; is_reconstructed?: boolean }[] | undefined,
  targetTimeMs: number,
  fallback: [number, number]
): InterpolatedVesselFix {
  const fallbackFix: InterpolatedVesselFix = {
    lon: fallback[0],
    lat: fallback[1],
    sog: 12.0,
    cog: 45.0,
    is_reconstructed: false,
  };

  if (!positions || positions.length === 0) return fallbackFix;

  const parsed = positions
    .map((p) => ({
      lon: p.lon,
      lat: p.lat,
      sog: typeof p.sog === 'number' && !isNaN(p.sog) ? p.sog : 12.0,
      cog: typeof p.cog === 'number' && !isNaN(p.cog) ? p.cog : 45.0,
      timeMs: new Date(p.timestamp).getTime(),
      is_reconstructed: Boolean(p.is_reconstructed),
    }))
    .filter((p) => !isNaN(p.timeMs))
    .sort((a, b) => a.timeMs - b.timeMs);

  if (parsed.length === 0) return fallbackFix;
  if (parsed.length === 1) {
    return {
      lon: parsed[0].lon,
      lat: parsed[0].lat,
      sog: parsed[0].sog,
      cog: parsed[0].cog,
      is_reconstructed: parsed[0].is_reconstructed,
    };
  }

  if (targetTimeMs <= parsed[0].timeMs) {
    return {
      lon: parsed[0].lon,
      lat: parsed[0].lat,
      sog: parsed[0].sog,
      cog: parsed[0].cog,
      is_reconstructed: parsed[0].is_reconstructed,
    };
  }
  if (targetTimeMs >= parsed[parsed.length - 1].timeMs) {
    const last = parsed[parsed.length - 1];
    return {
      lon: last.lon,
      lat: last.lat,
      sog: last.sog,
      cog: last.cog,
      is_reconstructed: last.is_reconstructed,
    };
  }

  for (let i = 0; i < parsed.length - 1; i++) {
    const p1 = parsed[i];
    const p2 = parsed[i + 1];
    if (targetTimeMs >= p1.timeMs && targetTimeMs <= p2.timeMs) {
      const span = p2.timeMs - p1.timeMs;
      const ratio = span > 0 ? (targetTimeMs - p1.timeMs) / span : 0;

      // Interpolate speed
      const interpSog = p1.sog + ratio * (p2.sog - p1.sog);

      // Compute geometric course over ground along segment
      const dLon = p2.lon - p1.lon;
      const dLat = p2.lat - p1.lat;
      const midLatRad = ((p1.lat + p2.lat) * 0.5 * Math.PI) / 180;
      let segCog = (Math.atan2(dLon * Math.cos(midLatRad), dLat) * 180) / Math.PI;
      if (segCog < 0) segCog += 360;

      const effectiveCog = Math.hypot(dLon, dLat) > 0.0001 ? segCog : p1.cog;
      const isRecon = Boolean(p1.is_reconstructed || p2.is_reconstructed);

      // Use Catmull-Rom spline if we have enough neighboring points and not across an AIS blackout gap
      if (parsed.length >= 4 && !p1.is_reconstructed && !p2.is_reconstructed) {
        const p0 = parsed[i > 0 ? i - 1 : 0];
        const p3 = parsed[i + 2 < parsed.length ? i + 2 : i + 1];
        const smoothLon = catmullRom1D(p0.lon, p1.lon, p2.lon, p3.lon, ratio);
        const smoothLat = catmullRom1D(p0.lat, p1.lat, p2.lat, p3.lat, ratio);
        return {
          lon: smoothLon,
          lat: smoothLat,
          sog: interpSog,
          cog: effectiveCog,
          is_reconstructed: isRecon,
        };
      }

      // Linear interpolation fallback for short tracks or blackout gaps
      return {
        lon: p1.lon + ratio * (p2.lon - p1.lon),
        lat: p1.lat + ratio * (p2.lat - p1.lat),
        sog: interpSog,
        cog: effectiveCog,
        is_reconstructed: isRecon,
      };
    }
  }

  return fallbackFix;
}

export function useVesselTracksLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  attribution: AttributionResult | null,
  detection: SlickDetection,
  selectedCandidateId: string | null,
  selectCandidate: (vesselId: string) => void,
  isVesselsVisible: boolean,
  isRoutesVisible: boolean
) {
  const playbackTimeHours = useOilTraceStore((s) => s.playbackTimeHours);
  const popupRef = useRef<maplibregl.Popup | null>(null);

  // 1. Static Routes, Discharge Gaps & Waypoints
  useEffect(() => {
    if (!map || !mapLoaded || !attribution?.candidates?.length) return;

    const routeSourceId = 'vessel-route-source';
    const dischargeSourceId = 'vessel-discharge-source';
    const waypointsSourceId = 'vessel-waypoints-source';
    const envelopeSourceId = 'vessel-envelope-source';

    const routeFeatures: any[] = [];
    const dischargeFeatures: any[] = [];
    const waypointFeatures: any[] = [];
    const envelopeFeatures: any[] = [];

    attribution.candidates.forEach((cand, cIdx) => {
      if (!cand.ais_positions || cand.ais_positions.length < 2) return;
      const isSelected = cand.vessel_id === (selectedCandidateId || attribution.candidates[0]?.vessel_id);

      // Speed-coded track segments
      for (let i = 1; i < cand.ais_positions.length; i++) {
        const p1 = cand.ais_positions[i - 1];
        const p2 = cand.ais_positions[i];
        const isGap = Boolean(p1.is_reconstructed || p2.is_reconstructed);
        if (isGap) continue; // handled by dischargeFeatures below

        const avgSog = ((p1.sog ?? 12.0) + (p2.sog ?? 12.0)) / 2;
        let segColor: string;
        if (avgSog >= 4.0 && avgSog <= 8.0) {
          segColor = '#F59E0B'; // Suspect discharge speed (amber: MARPOL 4.0-8.0 kn)
        } else if (avgSog > 12.0) {
          segColor = '#10B981'; // Cruising transit (emerald green)
        } else if (avgSog < 2.0) {
          segColor = '#94A3B8'; // Drifting / stationary (slate)
        } else {
          segColor = isSelected ? '#38BDF8' : cIdx === 0 ? '#EF4444' : '#64748B'; // Standard passage
        }

        const width = isSelected ? 3.5 : cIdx === 0 ? 2.5 : 1.5;
        const opacity = isSelected ? 0.95 : cIdx <= 2 ? 0.65 : 0.35;

        routeFeatures.push({
          type: 'Feature',
          properties: {
            vessel_id: cand.vessel_id,
            name: cand.vessel_name || cand.vessel_id,
            color: segColor,
            width,
            opacity,
            isSelected,
            sog: avgSog,
          },
          geometry: {
            type: 'LineString',
            coordinates: [
              [p1.lon, p1.lat],
              [p2.lon, p2.lat],
            ],
          },
        });
      }

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

              if (isSelected || cIdx === 0) {
                const corridor = buildCorridorPolygon(currentDischargeRun, 0.08);
                if (corridor.length > 0) {
                  envelopeFeatures.push({
                    type: 'Feature',
                    properties: {
                      vessel_id: cand.vessel_id,
                      vessel_name: cand.vessel_name,
                      label: 'AIS Blackout Dead-Reckoning Corridor',
                    },
                    geometry: { type: 'Polygon', coordinates: corridor },
                  });
                }
              }
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

        if (isSelected || cIdx === 0) {
          const corridor = buildCorridorPolygon(currentDischargeRun, 0.08);
          if (corridor.length > 0) {
            envelopeFeatures.push({
              type: 'Feature',
              properties: {
                vessel_id: cand.vessel_id,
                vessel_name: cand.vessel_name,
                label: 'AIS Blackout Dead-Reckoning Corridor',
              },
              geometry: { type: 'Polygon', coordinates: corridor },
            });
          }
        }
      }

      if (isSelected) {
        cand.ais_positions.forEach((p: any, idx: number) => {
          const isGap = Boolean(p.is_reconstructed);
          const isDischarge = !isGap && p.sog >= 2.0 && p.sog <= 6.0;
          const isCruising = !isGap && p.sog > 12.0;

          waypointFeatures.push({
            type: 'Feature',
            properties: {
              timestamp: p.timestamp,
              sog: p.sog,
              cog: p.cog,
              idx,
              isGap,
              isDischarge,
              isCruising,
            },
            geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
          });
        });
      }
    });

    const routeGeoJson: any = { type: 'FeatureCollection', features: routeFeatures };
    const dischargeGeoJson: any = { type: 'FeatureCollection', features: dischargeFeatures };
    const waypointFeaturesGeoJson: any = { type: 'FeatureCollection', features: waypointFeatures };
    const envelopeGeoJson: any = { type: 'FeatureCollection', features: envelopeFeatures };

    if (map.getSource(envelopeSourceId)) {
      (map.getSource(envelopeSourceId) as maplibregl.GeoJSONSource).setData(envelopeGeoJson);
    } else {
      map.addSource(envelopeSourceId, { type: 'geojson', data: envelopeGeoJson });
      map.addLayer({
        id: 'vessel-gap-envelope-fill',
        type: 'fill',
        source: envelopeSourceId,
        paint: {
          'fill-color': '#EF4444',
          'fill-opacity': 0.16,
        },
      });
      map.addLayer({
        id: 'vessel-gap-envelope-line',
        type: 'line',
        source: envelopeSourceId,
        paint: {
          'line-color': '#EF4444',
          'line-width': 1.6,
          'line-dasharray': [3, 2],
          'line-opacity': 0.8,
        },
      });
    }

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
      (map.getSource(waypointsSourceId) as maplibregl.GeoJSONSource).setData(waypointFeaturesGeoJson);
    } else {
      map.addSource(waypointsSourceId, { type: 'geojson', data: waypointFeaturesGeoJson });
      map.addLayer({
        id: 'vessel-route-waypoints',
        type: 'circle',
        source: waypointsSourceId,
        paint: {
          'circle-radius': ['case', ['get', 'isDischarge'], 4.5, 3.2],
          'circle-color': [
            'case',
            ['get', 'isGap'], '#EF4444',
            ['get', 'isDischarge'], '#F59E0B',
            ['get', 'isCruising'], '#10B981',
            '#38BDF8',
          ],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#060B11',
        },
      });
    }

    // Toggle route layers
    [
      'vessel-gap-envelope-fill',
      'vessel-gap-envelope-line',
      'vessel-route-line',
      'vessel-discharge-segments',
      'vessel-route-waypoints',
    ].forEach((layerId) => {
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
              popupRef.current = null;
            }
            selectCandidate(vid);
          }
        }
      });

      // Vessel hover
      map.on('mousemove', 'vessel-points', (e) => {
        if (!e.features || e.features.length === 0) return;
        map.getCanvas().style.cursor = 'pointer';
        const props = e.features[0].properties || {};
        const coords = (e.features[0].geometry as any).coordinates;

        if (!popupRef.current) {
          popupRef.current = new maplibregl.Popup({
            closeButton: false,
            closeOnClick: false,
            offset: 12,
          });
        }

        const html = `
          <div style="background:#0D1522; border:1px solid #1E2C3F; color:#E2E8F0; padding:8px 10px; font-family:monospace; font-size:11px; border-radius:3px; box-shadow:0 8px 24px rgba(0,0,0,0.7); min-width:180px;">
            <div style="font-weight:bold; color:#38BDF8; font-size:12px; margin-bottom:4px;">${props.vessel_name || props.vessel_id}</div>
            <div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span style="color:#64748B;">MMSI:</span><span>${props.vessel_id}</span></div>
            <div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span style="color:#64748B;">TYPE:</span><span>${props.type || 'Tanker'}</span></div>
            <div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span style="color:#64748B;">SPEED/COG:</span><span>${props.sog || 'N/A'} / ${props.cog || 'N/A'}</span></div>
            <div style="display:flex; justify-content:space-between; margin-bottom:2px;"><span style="color:#64748B;">RISK:</span><span style="color:${props.isSelected ? '#2DD4BF' : '#EF4444'}; font-weight:bold;">${props.score}</span></div>
            <div style="display:flex; justify-content:space-between;"><span style="color:#64748B;">SRC:</span><span style="color:#94A3B8;">${props.provenance || 'real_gfw'}</span></div>
            ${props.is_reconstructed ? '<div style="margin-top:5px; padding:3px 5px; background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.5); color:#FCA5A5; font-size:10px; font-weight:bold; text-align:center;">⚠ AIS GAP (DEAD-RECKONED FIX)</div>' : ''}
          </div>
        `;

        popupRef.current.setLngLat(coords).setHTML(html).addTo(map);
      });

      map.on('mouseleave', 'vessel-points', () => {
        map.getCanvas().style.cursor = '';
        if (popupRef.current) {
          popupRef.current.remove();
          popupRef.current = null;
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

  // Memoize candidates sorting once per candidate selection change
  const sortedCandidates = useMemo(() => {
    if (!attribution?.candidates?.length) return [];
    return [...attribution.candidates]
      .filter((c) => c.last_known_position)
      .sort((a, b) => {
        const isSelA = a.vessel_id === (selectedCandidateId || attribution.candidates[0]?.vessel_id);
        const isSelB = b.vessel_id === (selectedCandidateId || attribution.candidates[0]?.vessel_id);
        if (isSelA) return 1;
        if (isSelB) return -1;
        return (a.suspicion_score || 0) - (b.suspicion_score || 0);
      });
  }, [attribution?.candidates, selectedCandidateId]);

  // 3. Animate Candidate Vessels along 4D tracks with Scrubber
  useEffect(() => {
    if (!map || !mapLoaded || !sortedCandidates.length || !isVesselsVisible) return;

    const vesselSource = map.getSource('vessels-source') as maplibregl.GeoJSONSource | undefined;
    const headingSource = map.getSource('vessel-heading-source') as maplibregl.GeoJSONSource | undefined;
    if (!vesselSource || !headingSource) return;

    const detTimeMs = new Date(detection.detected_at).getTime();
    const currentScrubberTimeMs = detTimeMs + playbackTimeHours * 3600 * 1000;

    const updatedVesselFeatures: any[] = [];
    const updatedHeadingFeatures: any[] = [];

    sortedCandidates.forEach((c) => {
      const isSelected = c.vessel_id === (selectedCandidateId || attribution?.candidates?.[0]?.vessel_id);
      const score = c.suspicion_score || 0;
      const markerColor = isSelected ? '#2DD4BF' : score > 0.65 ? '#EF4444' : score > 0.4 ? '#F59E0B' : '#64748B';
      const fallbackPos = c.last_known_position as [number, number];
      const currentPos = getVesselPositionAtTime(c.ais_positions, currentScrubberTimeMs, fallbackPos);
      const posCoord: [number, number] = [currentPos.lon, currentPos.lat];

      const sog = currentPos.sog;
      const rawCog = currentPos.cog;
      const isInvalidCog = rawCog >= 360 || rawCog < 0 || isNaN(rawCog);
      const isStationary = sog < 0.8;
      const isReconstructed = currentPos.is_reconstructed;

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
          is_reconstructed: isReconstructed,
          isSelected,
          color: markerColor,
        },
        geometry: {
          type: 'Point' as const,
          coordinates: posCoord,
        },
      });

      if (!isInvalidCog && !isStationary) {
        const headingRad = (rawCog * Math.PI) / 180;
        const vecLen = Math.max(0.04, Math.min(0.20, (sog / 20) * 0.14));
        const tipLon = posCoord[0] + vecLen * Math.sin(headingRad);
        const tipLat = posCoord[1] + vecLen * Math.cos(headingRad);

        // Compute COG chevron arrowhead (150 deg barbs)
        const barbAngle = (150 * Math.PI) / 180;
        const barbLen = vecLen * 0.38;
        const leftBarbLon = tipLon + barbLen * Math.sin(headingRad + barbAngle);
        const leftBarbLat = tipLat + barbLen * Math.cos(headingRad + barbAngle);
        const rightBarbLon = tipLon + barbLen * Math.sin(headingRad - barbAngle);
        const rightBarbLat = tipLat + barbLen * Math.cos(headingRad - barbAngle);

        updatedHeadingFeatures.push({
          type: 'Feature' as const,
          properties: {
            vessel_id: c.vessel_id,
            color: markerColor,
            isSelected,
          },
          geometry: {
            type: 'LineString' as const,
            coordinates: [
              posCoord,
              [tipLon, tipLat],
              [leftBarbLon, leftBarbLat],
              [tipLon, tipLat],
              [rightBarbLon, rightBarbLat],
            ],
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
  }, [map, mapLoaded, sortedCandidates, playbackTimeHours, isVesselsVisible, detection.detected_at]);
}
