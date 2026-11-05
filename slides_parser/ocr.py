from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract

from .models import Region

DEFAULT_WINDOWS_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def default_tesseract_cmd() -> str | None:
    """TESSERACT_CMD env var, then tesseract on PATH, then the default Windows install path."""
    env = os.environ.get("TESSERACT_CMD")
    if env:
        return env
    if shutil.which("tesseract"):
        return None  # pytesseract will find it on its own
    if os.path.exists(DEFAULT_WINDOWS_TESSERACT):
        return DEFAULT_WINDOWS_TESSERACT
    return None


@dataclass
class OcrSettings:
    lang: str = "ukr+eng"
    psm: int = 6
    upscale: float = 2.0
    tesseract_cmd: str | None = None


class OcrEngine:
    """Preprocesses images and runs Tesseract on them."""

    def __init__(self, settings: OcrSettings | None = None):
        self.settings = settings or OcrSettings()
        cmd = self.settings.tesseract_cmd or default_tesseract_cmd()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        if self.settings.upscale != 1:
            gray = cv2.resize(
                gray, None, fx=self.settings.upscale, fy=self.settings.upscale,
                interpolation=cv2.INTER_CUBIC,
            )
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        # Tesseract works best with dark text on a light background. Light text on a
        # dark/colored block ends up as a mostly-black image after Otsu, so invert it.
        if np.count_nonzero(binary) < binary.size / 2:
            binary = cv2.bitwise_not(binary)
        return binary

    def read(self, image: np.ndarray) -> str:
        prepared = self.preprocess(image)
        text = pytesseract.image_to_string(
            prepared, lang=self.settings.lang, config=f"--psm {self.settings.psm}"
        )
        return text.strip()

    def read_region(self, image: np.ndarray, region: Region) -> str:
        height, width = image.shape[:2]
        clamped = region.clamped(width, height)
        if clamped is None:
            return ""
        crop = image[clamped.y:clamped.y + clamped.h, clamped.x:clamped.x + clamped.w]
        return self.read(crop)
