from __future__ import annotations

import json
from pathlib import Path

from .models import Region

LAYOUT_FILENAME = "regions.json"
FORMAT_VERSION = 1


class LayoutStore:
    """Persists the ordered list of OCR regions for every slide in a JSON file.

    File format::

        {"version": 1, "slides": {"1.jpg": [{"x": 0, "y": 0, "w": 100, "h": 50}, ...]}}

    The list order is the reading order. A slide without regions is read as a whole.
    """

    def __init__(self, path: Path, slides: dict[str, list[Region]] | None = None):
        self.path = path
        self._slides: dict[str, list[Region]] = slides or {}

    @classmethod
    def for_directory(cls, directory: Path) -> LayoutStore:
        return cls.load(directory / LAYOUT_FILENAME)

    @classmethod
    def load(cls, path: Path) -> LayoutStore:
        if not path.exists():
            return cls(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        slides = {
            name: [Region.from_dict(r) for r in regions]
            for name, regions in data.get("slides", {}).items()
        }
        return cls(path, slides)

    def get(self, name: str) -> list[Region]:
        return list(self._slides.get(name, []))

    def set(self, name: str, regions: list[Region]) -> None:
        if regions:
            self._slides[name] = list(regions)
        else:
            self._slides.pop(name, None)

    def save(self) -> None:
        data = {
            "version": FORMAT_VERSION,
            "slides": {name: [r.to_dict() for r in regions] for name, regions in self._slides.items()},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
