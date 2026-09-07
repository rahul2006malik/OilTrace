import { useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import { SlickDetection } from '../../../types';

export function usePhysicsProbeLayer(
  map: maplibregl.Map | null,
  mapLoaded: boolean,
  detection: SlickDetection,
  fetchPhysics: (lon: number, lat: number, timeIso?: string) => Promise<void>,
  togglePhysicsInspector: (open?: boolean) => void
) {
  useEffect(() => {
    if (!map || !mapLoaded) return;

    const clickHandler = (e: maplibregl.MapMouseEvent) => {
      // If click was on a vessel, let vessel layer handler deal with it
      const hitVessels = map.queryRenderedFeatures(e.point, { layers: ['vessel-points'] });
      if (hitVessels && hitVessels.length > 0) return;

      const clickLon = Number(e.lngLat.lng.toFixed(4));
      const clickLat = Number(e.lngLat.lat.toFixed(4));

      fetchPhysics(clickLon, clickLat, detection?.detected_at);
      togglePhysicsInspector(true);

      const reticleSource = map.getSource('sample-reticle-source') as maplibregl.GeoJSONSource | undefined;
      const reticleFeature = {
        type: 'Feature',
        properties: { lon: clickLon, lat: clickLat },
        geometry: { type: 'Point', coordinates: [clickLon, clickLat] },
      };

      if (reticleSource) {
        reticleSource.setData(reticleFeature as any);
      } else {
        map.addSource('sample-reticle-source', {
          type: 'geojson',
          data: reticleFeature as any,
        });

        map.addLayer({
          id: 'sample-reticle-ring',
          type: 'circle',
          source: 'sample-reticle-source',
          paint: {
            'circle-radius': 14,
            'circle-color': 'transparent',
            'circle-stroke-width': 2,
            'circle-stroke-color': '#2DD4BF',
            'circle-stroke-opacity': 0.85,
          },
        });

        map.addLayer({
          id: 'sample-reticle-core',
          type: 'circle',
          source: 'sample-reticle-source',
          paint: {
            'circle-radius': 3.5,
            'circle-color': '#2DD4BF',
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#060B11',
          },
        });
      }
    };

    map.on('click', clickHandler);
    return () => {
      map.off('click', clickHandler);
    };
  }, [map, mapLoaded, detection?.detected_at, fetchPhysics, togglePhysicsInspector]);
}
