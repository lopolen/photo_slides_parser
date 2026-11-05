"""Extract text from presentation slides saved as images."""

from .models import Region, SlideText
from .ocr import OcrEngine, OcrSettings
from .layout_store import LayoutStore
from .images import find_images, load_image
from .pipeline import extract_slide, extract_all, write_notes

__all__ = [
    "Region",
    "SlideText",
    "OcrEngine",
    "OcrSettings",
    "LayoutStore",
    "find_images",
    "load_image",
    "extract_slide",
    "extract_all",
    "write_notes",
]
