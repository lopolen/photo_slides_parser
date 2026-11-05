from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Region:
    """Rectangular area of a slide image, in image pixel coordinates."""

    x: int
    y: int
    w: int
    h: int

    def clamped(self, width: int, height: int) -> Region | None:
        """Return the part of the region that lies inside a `width` x `height` image."""
        x0 = max(0, min(self.x, width))
        y0 = max(0, min(self.y, height))
        x1 = max(0, min(self.x + self.w, width))
        y1 = max(0, min(self.y + self.h, height))
        if x1 - x0 < 1 or y1 - y0 < 1:
            return None
        return Region(x0, y0, x1 - x0, y1 - y0)

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_dict(cls, data: dict) -> Region:
        return cls(int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"]))


@dataclass
class SlideText:
    """OCR result for one slide: one text block per region, in reading order."""

    name: str
    blocks: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(b for b in self.blocks if b)
