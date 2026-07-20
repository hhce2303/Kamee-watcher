"""Zone model — named spatial regions in normalised image coordinates (Fase 4).

Zones partition a monitor's visible area into named regions (e.g. "entrance",
"cashier", "exit") that label detections and analytic events.  They are defined
in normalised coordinates (0..1 per axis) so the definition is resolution-
independent and can be persisted as plain JSON.
"""
from __future__ import annotations

from typing import List, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.analytics.models import BoundingBox


class Zone(BaseModel):
    """A named convex or concave polygon in normalised image space.

    Attributes:
        name: human-readable label (e.g. "entrance").
        vertices: polygon corners as (x, y) pairs in normalised coords.
            At least 3 vertices required; winding order (CW / CCW) is ignored.
        monitor_index: which monitor this zone applies to.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    vertices: Tuple[Tuple[float, float], ...]
    monitor_index: int = 0

    @field_validator("vertices")
    @classmethod
    def _at_least_three(cls, v: Tuple) -> Tuple:
        if len(v) < 3:
            raise ValueError("A zone polygon requires at least 3 vertices")
        return v

    def contains_center(self, bbox: BoundingBox) -> bool:
        """True when the bbox *centre point* lies inside the polygon (ray-cast)."""
        cx = bbox.x + bbox.w / 2.0
        cy = bbox.y + bbox.h / 2.0
        return _point_in_polygon(cx, cy, self.vertices)


def _point_in_polygon(
    x: float,
    y: float,
    vertices: Tuple[Tuple[float, float], ...],
) -> bool:
    """Even-odd ray-cast point-in-polygon test.  O(n) in vertex count."""
    n = len(vertices)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if (yi > y) != (yj > y):
            x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_intersect:
                inside = not inside
        j = i
    return inside


def zone_for_bbox(
    bbox: BoundingBox,
    monitor_index: int,
    zones: List[Zone],
) -> str | None:
    """Return the first zone name that contains *bbox* centre, or None."""
    for zone in zones:
        if zone.monitor_index == monitor_index and zone.contains_center(bbox):
            return zone.name
    return None
