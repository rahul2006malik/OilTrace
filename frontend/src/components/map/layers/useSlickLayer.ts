import { useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import { DriftRun, SlickDetection } from '../../../types';
import { useOilTraceStore } from '../../../store/useOilTraceStore';

export function useSlickLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  detection: SlickDetection,
  driftRun: DriftRun | null,
  isVisible: boolean
) {
  const playbackTimeHours = useOilTraceStore((s) => s.playbackTimeHours);
  useEffect(() => {
    if (!map || !mapLoaded || !detection) return;

    const slickSourceId = 'slick-source';
    const centroidSourceId = 'slick-centroid-source';

    const hasSlick = (detection.area_km2 || 0) > 0 && Array.isArray(detection.geometry?.coordinates) && detection.geometry.coordinates.length > 0;
    if (!hasSlick) {
      if (map.getSource(slickSourceId)) {
        (map.getSource(slickSourceId) as maplibregl.GeoJSONSource).setData({
          type: 'FeatureCollection',
          features: [],
        });
      }
      if (map.getSource(centroidSourceId)) {
        (map.getSource(centroidSourceId) as maplibregl.GeoJSONSource).setData({
          type: 'FeatureCollection',
          features: [],
        });
      }
      return;
    }

    // 1. Calculate spatiotemporal advection translation and Fay spreading shrinkage
    // Detection horizon is 0.0h; negative values (-1h to -48h) scrub backward in time.
    let dLon = 0;
    let dLat = 0;
    let scale = 1.0;
    let opacityMultiplier = 1.0;
    let effectiveArea = detection.area_km2;

    let onsetHours = 20.0;
    if (driftRun?.origin_zone?.estimated_onset_time && detection?.detected_at) {
      const onsetMs = new Date(driftRun.origin_zone.estimated_onset_time).getTime();
      const detMs = new Date(detection.detected_at).getTime();
      if (!isNaN(onsetMs) && !isNaN(detMs) && detMs > onsetMs) {
        const diffHours = (detMs - onsetMs) / (3600 * 1000);
        if (diffHours >= 1.0 && diffHours <= 48.0) {
          onsetHours = Math.round(diffHours * 10) / 10;
        }
      }
    }

    if (playbackTimeHours < -0.01) {
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

      if (driftRun?.members?.length) {
        // Normalization: -simWindowHours (origin) -> 0.0, 0.0h (detection horizon) -> 1.0
        const timeFraction = Math.max(0.0, Math.min(1.0, (playbackTimeHours + simWindowHours) / simWindowHours));
        
        let sumDlon = 0;
        let sumDlat = 0;
        let validMembers = 0;

        driftRun.members.forEach((m) => {
          const coords = m.backward_track.map((pt) => [pt.lon, pt.lat]);
          if (coords.length < 2) return;
          const exactIdx = (coords.length - 1) * timeFraction;
          const lowIdx = Math.floor(exactIdx);
          const highIdx = Math.min(coords.length - 1, lowIdx + 1);
          const subFrac = exactIdx - lowIdx;
          
          const curLon = coords[lowIdx][0] + (coords[highIdx][0] - coords[lowIdx][0]) * subFrac;
          const curLat = coords[lowIdx][1] + (coords[highIdx][1] - coords[lowIdx][1]) * subFrac;
          
          const endLon = coords[coords.length - 1][0];
          const endLat = coords[coords.length - 1][1];

          sumDlon += (curLon - endLon);
          sumDlat += (curLat - endLat);
          validMembers += 1;
        });

        if (validMembers > 0) {
          dLon = sumDlon / validMembers;
          dLat = sumDlat / validMembers;
        }
      } else {
        const progress = Math.min(1.0, Math.abs(playbackTimeHours) / simWindowHours);
        dLon = -0.15 * progress;
        dLat = -0.10 * progress;
      }

      // Fay spreading shrinkage looking backwards in time
      if (playbackTimeHours <= -onsetHours) {
        // Point release / nascent slick at vessel manifold
        scale = 0.18;
        opacityMultiplier = 0.25;
        effectiveArea = Math.max(0.2, detection.area_km2 * 0.05);
      } else {
        const hoursSinceDischarge = playbackTimeHours + onsetHours;
        const timeFracSinceDischarge = Math.max(0.05, Math.min(1.0, hoursSinceDischarge / onsetHours));
        scale = 0.25 + 0.75 * Math.pow(timeFracSinceDischarge, 0.375);
        opacityMultiplier = Math.min(1.0, 0.25 + timeFracSinceDischarge * 0.75);
        effectiveArea = detection.area_km2 * Math.pow(timeFracSinceDischarge, 0.75);
      }
    }

    // 2. Transform slick polygon coordinates
    const c0 = detection.centroid;
    const curCentroid: [number, number] = [
      Number((c0[0] + dLon).toFixed(5)),
      Number((c0[1] + dLat).toFixed(5)),
    ];

    const transformRing = (ring: number[][]) => {
      return ring.map(([lon, lat]) => [
        Number((curCentroid[0] + (lon - c0[0]) * scale).toFixed(5)),
        Number((curCentroid[1] + (lat - c0[1]) * scale).toFixed(5)),
      ]);
    };

    let transformedGeometry: any = detection.geometry;
    if (detection.geometry?.type === 'Polygon') {
      transformedGeometry = {
        type: 'Polygon',
        coordinates: (detection.geometry.coordinates as number[][][]).map(transformRing),
      };
    } else if (detection.geometry?.type === 'MultiPolygon') {
      transformedGeometry = {
        type: 'MultiPolygon',
        coordinates: (detection.geometry.coordinates as number[][][][]).map((poly) => poly.map(transformRing)),
      };
    }

    const isSimulated = Math.abs(playbackTimeHours) > 0.01;
    const slickGeoJson = {
      type: 'Feature' as const,
      properties: {
        name: isSimulated
          ? `Advected Oil Slick (T ${playbackTimeHours.toFixed(1)}h)`
          : 'Observed SAR Oil Slick',
        area: `${effectiveArea.toFixed(2)} km²`,
        confidence: `${(detection.oil_confidence * 100).toFixed(1)}%`,
        status: isSimulated ? 'Hindcast Advection State' : 'SAR Observation Horizon',
      },
      geometry: transformedGeometry,
    };

    const centroidGeoJson = {
      type: 'Feature' as const,
      properties: {
        name: `Slick Centroid (${curCentroid[0].toFixed(3)}°E, ${curCentroid[1].toFixed(3)}°N)`,
      },
      geometry: {
        type: 'Point' as const,
        coordinates: curCentroid,
      },
    };

    // 3. Slick Polygon Layers
    if (map.getSource(slickSourceId)) {
      (map.getSource(slickSourceId) as maplibregl.GeoJSONSource).setData(slickGeoJson);
    } else {
      map.addSource(slickSourceId, { type: 'geojson', data: slickGeoJson });

      map.addLayer({
        id: 'slick-glow',
        type: 'fill',
        source: slickSourceId,
        paint: {
          'fill-color': '#0284c7',
          'fill-opacity': 0.25,
        },
      });

      map.addLayer({
        id: 'slick-fill',
        type: 'fill',
        source: slickSourceId,
        paint: {
          'fill-color': '#2DD4BF',
          'fill-opacity': 0.55,
        },
      });

      map.addLayer({
        id: 'slick-line',
        type: 'line',
        source: slickSourceId,
        paint: {
          'line-color': '#2DD4BF',
          'line-width': 3,
        },
      });
    }

    // Dynamic Opacity Modulation based on spill onset
    if (map.getLayer('slick-fill')) {
      map.setPaintProperty('slick-fill', 'fill-opacity', 0.55 * opacityMultiplier);
    }
    if (map.getLayer('slick-glow')) {
      map.setPaintProperty('slick-glow', 'fill-opacity', 0.25 * opacityMultiplier);
    }
    if (map.getLayer('slick-line')) {
      map.setPaintProperty('slick-line', 'line-opacity', 1.0 * opacityMultiplier);
    }

    // 4. Centroid Marker Layers
    if (map.getSource(centroidSourceId)) {
      (map.getSource(centroidSourceId) as maplibregl.GeoJSONSource).setData(centroidGeoJson);
    } else {
      map.addSource(centroidSourceId, { type: 'geojson', data: centroidGeoJson });

      map.addLayer({
        id: 'slick-centroid-pulse',
        type: 'circle',
        source: centroidSourceId,
        paint: {
          'circle-radius': 14,
          'circle-color': '#2DD4BF',
          'circle-opacity': 0.2,
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#2DD4BF',
        },
      });

      map.addLayer({
        id: 'slick-centroid-core',
        type: 'circle',
        source: centroidSourceId,
        paint: {
          'circle-radius': 4,
          'circle-color': '#FFFFFF',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#060B11',
        },
      });
    }

    if (map.getLayer('slick-centroid-pulse')) {
      map.setPaintProperty('slick-centroid-pulse', 'circle-opacity', 0.2 * opacityMultiplier);
    }
    if (map.getLayer('slick-centroid-core')) {
      map.setPaintProperty('slick-centroid-core', 'circle-opacity', 1.0 * opacityMultiplier);
    }

    // Toggle visibility
    const slickLayers = ['slick-glow', 'slick-fill', 'slick-line', 'slick-centroid-pulse', 'slick-centroid-core'];
    slickLayers.forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isVisible && opacityMultiplier > 0 ? 'visible' : 'none');
      }
    });
  }, [map, mapLoaded, detection, driftRun, playbackTimeHours, isVisible]);
}
