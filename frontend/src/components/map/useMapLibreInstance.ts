import { useEffect, useRef, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { BasemapStyle, CursorCoords } from './types';
import { useOilTraceStore } from '../../store/useOilTraceStore';

export function getStyleDefinition(style: BasemapStyle, token?: string): any {
  if (style === 'mapbox' && token) {
    return `https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12?access_token=${token}`;
  }

  return {
    version: 8,
    sources: {
      'esri-imagery': {
        type: 'raster',
        tiles: [
          'https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: '© Esri, Maxar, Earthstar Geographics',
        maxzoom: 19,
      },
      'esri-labels': {
        type: 'raster',
        tiles: [
          'https://services.arcgisonline.com/arcgis/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: '© Esri',
        maxzoom: 19,
      },
      'esri-ocean': {
        type: 'raster',
        tiles: [
          'https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: '© Esri, GEBCO, NOAA',
        maxzoom: 16,
      },
      'esri-ocean-labels': {
        type: 'raster',
        tiles: [
          'https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: '© Esri',
        maxzoom: 16,
      },
      'esri-dark': {
        type: 'raster',
        tiles: [
          'https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: '© Esri, HERE, Garmin',
        maxzoom: 16,
      },
      'esri-dark-labels': {
        type: 'raster',
        tiles: [
          'https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: '© Esri',
        maxzoom: 16,
      },
    },
    layers: [
      {
        id: 'base-satellite',
        type: 'raster',
        source: 'esri-imagery',
        layout: { visibility: style === 'satellite' ? 'visible' : 'none' },
      },
      {
        id: 'labels-satellite',
        type: 'raster',
        source: 'esri-labels',
        layout: { visibility: style === 'satellite' ? 'visible' : 'none' },
      },
      {
        id: 'base-ocean',
        type: 'raster',
        source: 'esri-ocean',
        layout: { visibility: style === 'ocean' ? 'visible' : 'none' },
      },
      {
        id: 'labels-ocean',
        type: 'raster',
        source: 'esri-ocean-labels',
        layout: { visibility: style === 'ocean' ? 'visible' : 'none' },
      },
      {
        id: 'base-dark',
        type: 'raster',
        source: 'esri-dark',
        layout: { visibility: style === 'dark' ? 'visible' : 'none' },
      },
      {
        id: 'labels-dark',
        type: 'raster',
        source: 'esri-dark-labels',
        layout: { visibility: style === 'dark' ? 'visible' : 'none' },
      },
    ],
  };
}

export function useMapLibreInstance() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const prevSpillIdRef = useRef<string | null>(null);

  const detection = useOilTraceStore((s) => s.detection);
  const cameraTarget = useOilTraceStore((s) => s.cameraTarget);
  const setCameraTarget = useOilTraceStore((s) => s.setCameraTarget);
  const activeMapTab = useOilTraceStore((s) => s.activeMapTab);
  const activeScenarioId = useOilTraceStore((s) => s.activeScenarioId);
  const availableScenarios = useOilTraceStore((s) => s.availableScenarios);

  const [mapLoaded, setMapLoaded] = useState<boolean>(false);
  const [currentBasemap, setCurrentBasemap] = useState<BasemapStyle>('satellite');
  const [cursorCoords, setCursorCoords] = useState<CursorCoords | null>(null);
  const [mapboxToken, setMapboxToken] = useState<string>(() => localStorage.getItem('oiltrace_mapbox_token') || '');

  // Initialize MapLibre
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const initialStyle = getStyleDefinition(currentBasemap, mapboxToken);

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: initialStyle,
      center: [detection.centroid[0], detection.centroid[1]],
      zoom: 8.5,
      pitch: 25,
      bearing: 0,
      attributionControl: false,
    });

    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left');

    map.on('load', () => {
      mapRef.current = map;
      setMapLoaded(true);
    });

    map.on('mousemove', (e) => {
      setCursorCoords({
        lon: Number(e.lngLat.lng.toFixed(4)),
        lat: Number(e.lngLat.lat.toFixed(4)),
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Switch basemap layer dynamically
  const switchBasemap = useCallback((style: BasemapStyle, onRequireToken?: () => void) => {
    setCurrentBasemap(style);
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    if (style === 'mapbox') {
      if (!mapboxToken) {
        onRequireToken?.();
        return;
      }
      map.setStyle(`https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12?access_token=${mapboxToken}`);
      return;
    }

    ['satellite', 'ocean', 'dark'].forEach((name) => {
      const isCurrent = name === style;
      if (map.getLayer(`base-${name}`)) {
        map.setLayoutProperty(`base-${name}`, 'visibility', isCurrent ? 'visible' : 'none');
      }
      if (map.getLayer(`labels-${name}`)) {
        map.setLayoutProperty(`labels-${name}`, 'visibility', isCurrent ? 'visible' : 'none');
      }
    });
  }, [mapLoaded, mapboxToken]);

  // Synchronize Camera on incident or scenario change (fit bounding box if available)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    if (cameraTarget) {
      map.flyTo({
        center: cameraTarget,
        zoom: 8.5,
        speed: 1.2,
      });
      setCameraTarget(null);
      return;
    }

    if (detection?.centroid && detection.spill_id !== prevSpillIdRef.current) {
      prevSpillIdRef.current = detection.spill_id;

      const activeScen = availableScenarios.find((s) => s.scenario_id === activeScenarioId);
      if (activeScen?.bbox && activeScen.bbox.length === 4) {
        const [minLon, minLat, maxLon, maxLat] = activeScen.bbox;
        map.fitBounds(
          [
            [minLon, minLat],
            [maxLon, maxLat],
          ],
          { padding: 75, maxZoom: 10.5, duration: 1200 }
        );
      } else {
        map.flyTo({
          center: [detection.centroid[0], detection.centroid[1]],
          zoom: 8.5,
          speed: 1.2,
        });
      }
    }
  }, [cameraTarget, detection?.spill_id, mapLoaded, setCameraTarget, detection?.centroid, activeScenarioId, availableScenarios]);

  // Synchronize Active Map Tab with Basemap
  useEffect(() => {
    if (!mapRef.current || !mapLoaded) return;
    if (activeMapTab === 'Satellite') {
      switchBasemap('satellite');
    } else if (activeMapTab === 'Map') {
      switchBasemap('dark');
    } else if (activeMapTab === 'Ocean Currents') {
      switchBasemap('ocean');
    }
  }, [activeMapTab, mapLoaded, switchBasemap]);

  return {
    mapContainer,
    mapRef,
    mapLoaded,
    currentBasemap,
    switchBasemap,
    cursorCoords,
    mapboxToken,
    setMapboxToken,
  };
}
