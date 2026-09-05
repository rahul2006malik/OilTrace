/**
 * Shared MapLibre GL map instance context.
 *
 * Extracted to its own module to break circular imports between
 * ChartCanvas (which renders layer components) and the layer components
 * (which need the map instance). ChartCanvas provides the value via
 * MapProvider; every layer reads it via useMap().
 */

import { createContext, useContext } from "react";
import type maplibregl from "maplibre-gl";

const MapInstanceContext = createContext<maplibregl.Map | null>(null);

export const MapProvider = MapInstanceContext.Provider;

/**
 * Returns the current MapLibre map instance, or null if the map is not yet
 * loaded. Layer components should early-return when null.
 */
export function useMap(): maplibregl.Map | null {
  return useContext(MapInstanceContext);
}
