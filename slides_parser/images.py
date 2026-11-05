from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")


def natural_key(name: str) -> list:
    """Sort key so that '2.jpg' comes before '10.jpg'."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def find_images(directory: Path) -> list[Path]:
    """All supported images in `directory`, naturally sorted by filename."""
    if not directory.is_dir():
        return []
    images = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(images, key=lambda p: natural_key(p.name))


def load_image(path: Path) -> np.ndarray:
    """Read an image as BGR. Works with non-ASCII paths, unlike cv2.imread on Windows."""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot read image: {path}")
    return image
