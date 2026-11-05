from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .images import find_images
from .layout_store import LAYOUT_FILENAME, LayoutStore
from .ocr import OcrEngine, OcrSettings
from .pipeline import extract_all, write_notes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract text from presentation slides saved as images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Without --cli the graphical region editor opens.\n"
            "Images are processed in natural filename order (1.jpg, 2.jpg, ..., 10.jpg).\n"
            f"If the input directory contains {LAYOUT_FILENAME} (created by the GUI), only the\n"
            "marked regions are read, in their numbered order. Otherwise the whole slide is read.\n"
            "Caution: the output file is overwritten."
        ),
    )
    parser.add_argument("-i", "--input", type=Path, default=Path("input"),
                        help="Directory with slide images, or a single image file (default: input/).")
    parser.add_argument("-o", "--output", type=Path, default=Path("output.txt"),
                        help="Output text file (default: output.txt).")
    parser.add_argument("--regions", type=Path, default=None,
                        help=f"Regions file (default: <input>/{LAYOUT_FILENAME}).")
    parser.add_argument("--ignore-regions", action="store_true",
                        help="Read whole slides even if a regions file exists.")
    parser.add_argument("--lang", default="ukr+eng", help="Tesseract languages (default: ukr+eng).")
    parser.add_argument("--psm", type=int, default=6, help="Tesseract page segmentation mode (default: 6).")
    parser.add_argument("--tesseract", default=None, help="Path to the tesseract executable.")
    parser.add_argument("--cli", action="store_true",
                        help="Run in the console without the GUI (by default the GUI region editor opens).")
    return parser


def settings_from_args(args: argparse.Namespace) -> OcrSettings:
    return OcrSettings(lang=args.lang, psm=args.psm, tesseract_cmd=args.tesseract)


def run_cli(args: argparse.Namespace) -> int:
    input_path: Path = args.input
    if input_path.is_file():
        # A single image: its regions (if any) live in regions.json next to it.
        input_dir, images = input_path.parent, [input_path]
    else:
        input_dir = input_path
        if not input_dir.exists():
            input_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created '{input_dir}'. Put slide images there and run again.")
            return 1
        images = find_images(input_dir)
    if not images:
        print(f"No images found in '{input_dir}'.")
        return 1

    store = None
    if not args.ignore_regions:
        store = LayoutStore.load(args.regions) if args.regions else LayoutStore.for_directory(input_dir)

    engine = OcrEngine(settings_from_args(args))

    def progress(index: int, total: int, path: Path) -> None:
        mode = "regions" if store and store.get(path.name) else "full slide"
        print(f"[{index + 1}/{total}] {path.name} ({mode})")

    write_notes(args.output, extract_all(engine, images, store, progress))
    print(f"\nAll extracted text has been saved to {args.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.cli:
        from .gui import run_gui
        return run_gui(input_dir=args.input, output=args.output, settings=settings_from_args(args))
    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
