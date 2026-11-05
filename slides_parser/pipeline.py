from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from .images import load_image
from .layout_store import LayoutStore
from .models import Region, SlideText
from .ocr import OcrEngine

ProgressCallback = Callable[[int, int, Path], None]


def extract_slide(engine: OcrEngine, image_path: Path, regions: list[Region]) -> SlideText:
    """OCR one slide. With regions, read each in order; without, read the whole image."""
    image = load_image(image_path)
    if regions:
        blocks = [engine.read_region(image, r) for r in regions]
    else:
        blocks = [engine.read(image)]
    return SlideText(image_path.name, blocks)


def extract_all(
    engine: OcrEngine,
    image_paths: list[Path],
    store: LayoutStore | None = None,
    on_progress: ProgressCallback | None = None,
) -> Iterator[SlideText]:
    total = len(image_paths)
    for index, path in enumerate(image_paths):
        if on_progress:
            on_progress(index, total, path)
        regions = store.get(path.name) if store else []
        yield extract_slide(engine, path, regions)


def write_notes(output_file: Path, slides: Iterable[SlideText]) -> None:
    """Write all slides to `output_file` (overwriting it), separated by blank lines."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for slide in slides:
            f.write(slide.text)
            f.write("\n\n")
