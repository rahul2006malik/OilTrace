export type BasemapStyle = 'satellite' | 'ocean' | 'dark' | 'mapbox';

export interface ActiveLayersState {
  slick: boolean;
  cones: boolean;
  streamlines: boolean;
  vessels: boolean;
  routes: boolean;
  wind: boolean;
  eez: boolean;
}

export interface CursorCoords {
  lon: number;
  lat: number;
}
