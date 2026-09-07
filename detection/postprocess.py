"""
detection/postprocess.py — SIH26143 Detection subsystem

Raster -> vector post-processing: converts a continuous oil-probability
map (as produced by detection/detector.py's Stage 2 segmenter) into a
schemas.md-compliant `slick_detection.geojson` dictionary, with
geo-referenced polygon geometry and physical/morphological features
(area, elongation, centroid, thickness proxy).

Ground truth for the OUTPUT SHAPE: schemas.md §1 (`slick_detection.geojson`).
Ground truth for the PHYSICS/HEURISTICS: SIH26143_Project_Document.md §5.5.

------------------------------------------------------------------------
READ BEFORE WIRING THIS INTO A DEMO — two honesty notes, not hedges:
------------------------------------------------------------------------

1. `lookalike_suppressed` is hardcoded to False by the caller (detector.py)
   and simply threaded through here. Project Doc §5.4 describes a SEPARATE
   second-stage per-blob classifier (GLCM texture + shape features on
   connected components) that would set this flag. Detection_Model_
   Documentation.md confirms that classifier was never built — the shipped
   model handles look-alikes purely as whole-scene hard negatives baked
   into classifier+segmenter training, with no per-blob verdict anywhere
   in the pipeline. Shipping `lookalike_suppressed: True` on every blob
   would misrepresent a capability that doesn't exist; shipping `False`
   is the honest statement of "not implemented," and this file will not
   silently invent a passing verdict. If that classifier gets built later,
   wire its real per-blob output in through the `lookalike_suppressed`
   parameter — don't hardcode it there either.

2. `thickness_class` is a coarse, UNCALIBRATED proxy (VV/VH backscatter
   damping contrast). The thresholds below are literature-informed
   starting points, not a fitted/validated retrieval — Project Doc §5.5
   says this explicitly ("proxy classification ... not full quad-pol
   decomposition") and that framing is preserved here. Calibrate against
   MV Rak / Ennore or held-out labeled thickness data before quoting this
   field as anything beyond illustrative in a demo.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple
import uuid

import cv2
import numpy as np
from pyproj import Geod
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union

_GEOD = Geod(ellps="WGS84")

# Standard GeoTIFF geolocation tag numbers (not name-based lookup — tifffile's
# tag-name registry for extended/GeoTIFF tags isn't guaranteed stable across
# versions, numeric tag codes are).
_TAG_MODEL_PIXEL_SCALE = 33550
_TAG_MODEL_TIEPOINT = 33922

# Fallback anchor when NEITHER embedded GeoTIFF tags NOR an explicit
# geo_bounds/center_lonlat are available: Arabian Sea / Mumbai offshore
# corridor, per the task spec, so downstream Drift physics always has a
# real, plausible coordinate to simulate from. This is a DEMONSTRATION
# placeholder, not a detection — never present a geometry georeferenced
# this way as a real scene location without saying so on-screen.
DEFAULT_DEMO_ANCHOR_LONLAT: Tuple[float, float] = (72.5, 18.8)

_MIN_CONTOUR_AREA_PX_DEFAULT = 50
_SIMPLIFY_TOLERANCE_PX_DEFAULT = 1.5

# --- Thickness-proxy thresholds (dB) --------------------------------------
# damping = mean(background backscatter) - mean(oil-pixel backscatter), so
# larger positive values mean the oil region is more strongly suppressed
# relative to surrounding water. See module docstring note (2) above.
_VV_THICK_DB = 6.0
_VH_THICK_DB = 4.0
_VV_THIN_DB = 3.0
_VH_THIN_DB = 1.0


def try_read_geotiff_georeference(image_path: str) -> Optional[Callable[[float, float], Tuple[float, float]]]:
    """Best-effort read of standard GeoTIFF ModelPixelScale/ModelTiepoint
    tags via tifffile. Returns a pixel(col, row) -> (lon, lat) callable, or
    None if the file carries no recognizable geo tags.

    Expected to return None for this project's Zenodo Sentinel-1 Sigma0-dB
    crops (Detection_Model_Documentation.md §3 — plain SAR crops, not
    georeferenced products) — this is a best-effort path for scenes that DO
    carry real georeferencing (e.g. a live Copernicus pull), not an
    assumption that the training/eval data will.
    """
    try:
        import tifffile
    except ImportError:
        return None

    try:
        with tifffile.TiffFile(image_path) as tif:
            tags = tif.pages[0].tags
            pixel_scale_tag = tags.get(_TAG_MODEL_PIXEL_SCALE)
            tiepoint_tag = tags.get(_TAG_MODEL_TIEPOINT)
            if pixel_scale_tag is None or tiepoint_tag is None:
                return None
            sx, sy = pixel_scale_tag.value[0], pixel_scale_tag.value[1]
            i, j, _k, x0, y0, _z0 = tiepoint_tag.value[:6]
    except Exception:
        # Any malformed/partial tag read falls back to geo_bounds/center_lonlat/
        # default-anchor georeferencing rather than raising — a missing/broken
        # geo tag on one scene shouldn't take down the whole detection call.
        return None

    def transform(col: float, row: float) -> Tuple[float, float]:
        lon = x0 + (col - i) * sx
        lat = y0 - (row - j) * sy
        return lon, lat

    return transform


def _build_pixel_to_lonlat(
    image_shape: Tuple[int, int],
    geo_bounds: Optional[Tuple[float, float, float, float]] = None,
    center_lonlat: Optional[Tuple[float, float]] = None,
    pixel_resolution_m: float = 10.0,
) -> Callable[[float, float], Tuple[float, float]]:
    """Fallback georeferencer used when no embedded GeoTIFF tags are found.

    - If `geo_bounds` (min_lon, min_lat, max_lon, max_lat) is given: linear
      interpolation across the scene extent. Adequate for a ~2048px scene
      at ~10m/px (~20km across) where the bbox is already known.
    - Else, anchor on `center_lonlat` (or DEFAULT_DEMO_ANCHOR_LONLAT) and
      use a proper geodesic direct-problem solve (pyproj Geod.fwd) from
      pixel-offset-in-metres to lon/lat, rather than a flat-Earth
      degrees-per-metre approximation.
    """
    h, w = image_shape[:2]

    if geo_bounds is not None:
        min_lon, min_lat, max_lon, max_lat = geo_bounds

        def transform_bbox(col: float, row: float) -> Tuple[float, float]:
            lon = min_lon + (col / max(w - 1, 1)) * (max_lon - min_lon)
            lat = max_lat - (row / max(h - 1, 1)) * (max_lat - min_lat)  # row 0 = top = max_lat
            return lon, lat

        return transform_bbox

    anchor_lon, anchor_lat = center_lonlat if center_lonlat is not None else DEFAULT_DEMO_ANCHOR_LONLAT

    def transform_anchor(col: float, row: float) -> Tuple[float, float]:
        dx_m = (col - w / 2.0) * pixel_resolution_m
        dy_m = (h / 2.0 - row) * pixel_resolution_m  # image row grows downward -> south
        dist_m = math.hypot(dx_m, dy_m)
        if dist_m < 1e-6:
            return anchor_lon, anchor_lat
        azimuth_deg = math.degrees(math.atan2(dx_m, dy_m))  # bearing from north, clockwise
        lon, lat, _back_az = _GEOD.fwd(anchor_lon, anchor_lat, azimuth_deg, dist_m)
        return lon, lat

    return transform_anchor


def _geodesic_area_km2(geom) -> float:
    """Geodesic (WGS84 ellipsoid) area of a Polygon or MultiPolygon, in km2."""
    if geom is None or geom.is_empty:
        return 0.0

    def _single_area_m2(poly: Polygon) -> float:
        if poly is None or poly.is_empty or not hasattr(poly, "exterior") or poly.exterior is None:
            return 0.0
        try:
            area_m2, _perimeter_m = _GEOD.geometry_area_perimeter(poly)
            return abs(area_m2)  # sign depends on ring winding direction, not meaningful here
        except Exception:
            return 0.0

    if isinstance(geom, MultiPolygon):
        total_m2 = sum(_single_area_m2(p) for p in geom.geoms)
    elif isinstance(geom, Polygon):
        total_m2 = _single_area_m2(geom)
    else:
        total_m2 = 0.0
    return float(total_m2 / 1.0e6)


def _estimate_thickness_class(raw_scene: np.ndarray, oil_mask: np.ndarray) -> str:
    """VV/VH backscatter-damping proxy for oil thickness class.

    `raw_scene` must be the RAW (non-percentile-normalized) Sigma0-dB array
    — the dB thresholds above are only meaningful against actual dB values,
    not a [0,1]-clipped model-input representation. See detector.py, which
    deliberately re-reads the raw TIFF for this reason rather than reusing
    the normalized array that went into the model.
    """
    vv = raw_scene[..., 0].astype(np.float32)
    has_vh = raw_scene.shape[-1] > 1
    vh = raw_scene[..., 1].astype(np.float32) if has_vh else None

    bg_mask = ~oil_mask
    if not oil_mask.any() or not bg_mask.any():
        # Can't compute a damping contrast without both an oil region and a
        # background region present (e.g. oil fills the entire crop) — "thin"
        # is a deliberately non-committal default, not a confident guess.
        return "thin"

    vv_damping = float(vv[bg_mask].mean() - vv[oil_mask].mean())
    vh_damping = float(vh[bg_mask].mean() - vh[oil_mask].mean()) if has_vh else 0.0

    if has_vh:
        if vv_damping >= _VV_THICK_DB and vh_damping >= _VH_THICK_DB:
            return "thick"
        if vv_damping >= _VV_THIN_DB and vh_damping >= _VH_THIN_DB:
            return "thin"
    else:
        if vv_damping >= _VV_THICK_DB:
            return "thick"
        if vv_damping >= _VV_THIN_DB:
            return "thin"
    return "sheen"


def mask_to_geojson(
    prob_map: np.ndarray,
    raw_scene: np.ndarray,
    classify_confidence: float,
    *,
    threshold: float = 0.5,
    min_area_px: int = _MIN_CONTOUR_AREA_PX_DEFAULT,
    simplify_tolerance_px: float = _SIMPLIFY_TOLERANCE_PX_DEFAULT,
    pixel_resolution_m: float = 10.0,
    geo_bounds: Optional[Tuple[float, float, float, float]] = None,
    center_lonlat: Optional[Tuple[float, float]] = None,
    geotiff_transform: Optional[Callable[[float, float], Tuple[float, float]]] = None,
    spill_id: Optional[str] = None,
    detected_at: Optional[str] = None,
    source_scene_id: Optional[str] = None,
    lookalike_suppressed: bool = False,
) -> Optional[dict]:
    """Convert a probability map + raw scene into a schemas.md-compliant
    `slick_detection.geojson` dict, or None if no slick survives thresholding.

    Args:
        prob_map: (H, W) float array, oil probability per pixel, ALREADY
            upsampled to the native scene resolution (this function does no
            resizing of its own — detector.py's predict_full_scene_wholescene
            already returns native-resolution output).
        raw_scene: (H, W, C) RAW (non-normalized) Sigma0-dB array, C>=1,
            channel 0 = VV, channel 1 = VH if present. Used for the
            thickness-class proxy, not for geometry.
        classify_confidence: Stage 1 classifier's P(oil) for this scene —
            multiplied into oil_confidence per the task spec (segmentation
            confidence alone doesn't account for the gate having been
            uncertain in the first place).
        geotiff_transform: if given, takes priority over geo_bounds/
            center_lonlat entirely (pass the callable from
            try_read_geotiff_georeference() when available).

    Returns:
        dict matching schemas.md §1, or None.
    """
    if prob_map.ndim != 2:
        raise ValueError(f"prob_map must be 2D (H, W); got shape {prob_map.shape}")
    if raw_scene.ndim != 3 or raw_scene.shape[-1] < 1:
        raise ValueError(f"raw_scene must be (H, W, C) with C>=1; got shape {raw_scene.shape}")
    if prob_map.shape != raw_scene.shape[:2]:
        raise ValueError(
            f"prob_map spatial shape {prob_map.shape} != raw_scene spatial shape "
            f"{raw_scene.shape[:2]} — did you upsample prob_map to native resolution "
            f"before calling this?"
        )

    # --- 1. Threshold + contour extraction --------------------------------
    binary_mask = (prob_map >= threshold).astype(np.uint8)
    if binary_mask.sum() == 0:
        return None

    contours, _hierarchy = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    surviving = [c for c in contours if cv2.contourArea(c) >= min_area_px]
    if not surviving:
        return None

    # --- 2. Polygonize (pixel space) + union multiple slicks ---------------
    # RETR_EXTERNAL was requested deliberately (task spec) -> no interior
    # rings/holes to handle.
    pixel_polygons = []
    for c in surviving:
        pts = c.squeeze(axis=1)
        if pts.ndim != 2 or pts.shape[0] < 3:
            continue
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_empty:
            pixel_polygons.append(poly)
    if not pixel_polygons:
        return None

    unified_pixel_geom = unary_union(pixel_polygons)
    if unified_pixel_geom.is_empty:
        return None
    unified_pixel_geom = unified_pixel_geom.simplify(simplify_tolerance_px, preserve_topology=True)

    # --- 3. Elongation ratio, in PIXEL space, from the dominant blob ------
    # (Simplification/georeferencing distort angles/ratios — compute this
    # from the raw, largest surviving contour instead of the output geometry.)
    largest_contour = max(surviving, key=cv2.contourArea)
    (_cx, _cy), (rect_w, rect_h), _angle = cv2.minAreaRect(largest_contour)
    elongation_ratio = float(max(rect_w, rect_h) / max(min(rect_w, rect_h), 1.0))

    # --- 4. Cleaned mask (surviving contours only) for stats --------------
    cleaned_mask = np.zeros_like(binary_mask)
    cv2.drawContours(cleaned_mask, surviving, -1, color=1, thickness=-1)
    cleaned_mask = cleaned_mask.astype(bool)

    oil_pixel_probs = prob_map[cleaned_mask]
    mean_seg_prob = float(oil_pixel_probs.mean()) if oil_pixel_probs.size else 0.0
    oil_confidence = float(np.clip(mean_seg_prob * classify_confidence, 0.0, 1.0))

    thickness_class = _estimate_thickness_class(raw_scene, cleaned_mask)

    # --- 5. Georeferencing: pixel space -> WGS84 lon/lat -------------------
    if geotiff_transform is not None:
        transform_fn = geotiff_transform
    else:
        transform_fn = _build_pixel_to_lonlat(
            image_shape=prob_map.shape,
            geo_bounds=geo_bounds,
            center_lonlat=center_lonlat,
            pixel_resolution_m=pixel_resolution_m,
        )

    geo_geom = shapely_transform(transform_fn, unified_pixel_geom)
    if geo_geom is None or geo_geom.is_empty:
        return None

    centroid_pt = geo_geom.centroid
    centroid = [
        float(np.clip(centroid_pt.x, -180.0, 180.0)),
        float(np.clip(centroid_pt.y, -90.0, 90.0)),
    ]  # [lon, lat]
    area_km2 = _geodesic_area_km2(geo_geom)

    # --- 6. Assemble schemas.md-compliant output ---------------------------
    resolved_spill_id = spill_id or f"spill_{uuid.uuid4().hex[:12]}"
    resolved_detected_at = detected_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    resolved_scene_id = source_scene_id or "UNKNOWN_SCENE"

    return {
        "spill_id": resolved_spill_id,
        "detected_at": resolved_detected_at,
        "geometry": json.loads(json.dumps(mapping(geo_geom))),
        "centroid": centroid,
        "area_km2": area_km2,
        "elongation_ratio": elongation_ratio,
        "oil_confidence": oil_confidence,
        "lookalike_suppressed": bool(lookalike_suppressed),
        "thickness_class": thickness_class,
        "source_scene_id": resolved_scene_id,
        "data_provenance": "real_detector",
    }
