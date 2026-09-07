import { useEffect } from 'react';
import maplibregl from 'maplibre-gl';

export function useMaritimeBoundariesLayer(map: maplibregl.Map | null, mapLoaded: boolean, isVisible: boolean) {
  useEffect(() => {
    if (!map || !mapLoaded) return;

    const eezSourceId = 'indian-eez-source';
    if (!map.getSource(eezSourceId)) {
      map.addSource(eezSourceId, {
        type: 'geojson',
        data: '/indian_maritime_boundaries.geojson',
      });

      // EEZ 200 NM Line (Gold Dashed)
      map.addLayer({
        id: 'indian-eez-line',
        type: 'line',
        source: eezSourceId,
        filter: ['==', ['get', 'boundary_type'], 'EEZ'],
        paint: {
          'line-color': '#F59E0B',
          'line-width': 2,
          'line-dasharray': [4, 3],
          'line-opacity': 0.85,
        },
      });

      // Territorial Waters 12 NM Line (Emerald)
      map.addLayer({
        id: 'indian-territorial-line',
        type: 'line',
        source: eezSourceId,
        filter: ['==', ['get', 'boundary_type'], 'TERRITORIAL'],
        paint: {
          'line-color': '#10B981',
          'line-width': 1.5,
          'line-dasharray': [2, 2],
          'line-opacity': 0.8,
        },
      });
    }

    // Toggle visibility
    ['indian-eez-line', 'indian-territorial-line'].forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none');
      }
    });
  }, [map, mapLoaded, isVisible]);
}
