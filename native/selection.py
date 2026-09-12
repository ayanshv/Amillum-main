"""Selection geometry in desktop points, with a bottom-left origin.

No pixels, document content, capture operations, or approval are represented here.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def clamp(self, point: Point) -> Point:
        return Point(max(self.x, min(point.x, self.x + self.width)),
                     max(self.y, min(point.y, self.y + self.height)))

    def contains(self, point: Point) -> bool:
        return self.x <= point.x <= self.x + self.width and self.y <= point.y <= self.y + self.height

    @classmethod
    def between(cls, first: Point, second: Point):
        return cls(min(first.x, second.x), min(first.y, second.y),
                   abs(first.x - second.x), abs(first.y - second.y))


@dataclass(frozen=True)
class Display:
    identifier: int
    bounds: Rect
    scale: float


class Phase(Enum):
    IDLE = 'idle'
    SELECTING = 'selecting'
    SELECTED = 'selected'


class Selection:
    MINIMUM_SIZE = 8.0

    def __init__(self):
        self.phase = Phase.IDLE
        self.display: Optional[Display] = None
        self.origin: Optional[Point] = None
        self.rect: Optional[Rect] = None

    def activate(self) -> bool:
        if self.phase is not Phase.IDLE:
            return False
        self.phase = Phase.SELECTING
        return True

    def begin(self, display: Display, point: Point) -> bool:
        if self.phase is not Phase.SELECTING or self.origin is not None:
            return False
        self.display = display
        self.origin = display.bounds.clamp(point)
        self.rect = Rect.between(self.origin, self.origin)
        return True

    def move(self, point: Point):
        if self.phase is Phase.SELECTING and self.origin is not None:
            self.rect = Rect.between(self.origin, self.display.bounds.clamp(point))

    def finish(self, point: Point) -> bool:
        if self.phase is not Phase.SELECTING or self.origin is None:
            return False
        self.move(point)
        if self.rect.width < self.MINIMUM_SIZE or self.rect.height < self.MINIMUM_SIZE:
            self.display = self.origin = self.rect = None
            return False
        self.phase = Phase.SELECTED
        self.origin = None
        return True

    def cancel(self):
        self.phase = Phase.IDLE
        self.display = self.origin = self.rect = None

