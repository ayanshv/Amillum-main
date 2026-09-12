"""Geometry-only attachment for a future mascot; deliberately renders nothing."""

from typing import Optional
from native.selection import Point, Rect


class MascotAnchor:
    def __init__(self):
        self.position: Optional[Point] = None

    def update(self, rect: Optional[Rect]):
        self.position = None if rect is None else Point(rect.x + rect.width / 2, rect.y)

