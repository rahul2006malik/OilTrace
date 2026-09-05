"""
detection package — SIH26143 Detection & Characterization subsystem.

Public API surface for other subsystems (Drift, Attribution) and the
Integration+Frontend layer. Import from here, not from
`detection.detector` / `detection.postprocess` directly, so this file
stays the actual contract boundary if internals get reorganized later.
"""

from .detector import OilSpillDetector
from .postprocess import mask_to_geojson

__all__ = ["OilSpillDetector", "mask_to_geojson"]
