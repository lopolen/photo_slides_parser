import cv2
import pytesseract
from pathlib import Path
import argparse
from itertools import chain


pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Extract text from images in a directory.",
                                     epilog="Information would be sorted by filename so I would recomend to name the files like 1.jps, 2.jpg, 3.jpg etc. or 1.png, 2.png, 3.png etc.\n\
                                     Caution: If output.txt already exists, it will be overwritten. Please make sure to back up any important data before running the script.")
    parser.add_argument(
        "-i", "--input", type=str, default="input/", help="Input directory containing images."
    )
    parser.add_argument(
        "-o", "--output", type=str, default="output.txt", help="Output text file."
    )
    return parser.parse_args()


def get_text_from_image(image_path: Path) -> str:
    img = cv2.imread(str(image_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # збільшення + бінаризація часто суттєво покращують результат
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    text = pytesseract.image_to_string(gray, lang="ukr+end", config="--psm 6")
    return text


def process_images_in_directory(input_dir: Path, output_file: Path):
    image_paths_unsorted = list(chain(input_dir.glob("*.jpg"), input_dir.glob("*.png")))
    image_paths = sorted(image_paths_unsorted, key=lambda x: x.name)  # Sort by filename

    for image_path in image_paths:
        print(f"Processing {image_path.name}...")
        text = get_text_from_image(image_path)

        with open(output_file, "a", encoding="utf-8") as f:
            f.write(text)
            f.write("\n\n")  # Add a newline between texts from different images
        
        print(f"Extracted text saved to {output_file}")


if __name__ == "__main__":
    parser = parse_arguments()

    if not Path("input/").exists():
        Path("input/").mkdir(parents=True, exist_ok=True)
        parser.print_help()
        exit(1)

    if Path("input/").is_dir() and len(list(Path("input/").glob("*.jpg"))) == 0:
        print("No .jpg files found in the 'input/' directory.")
        exit(1)

    output_file = Path("output.txt")

    if output_file.exists():
        output_file.unlink()  # Remove the existing output file to avoid appending to old data
    else:
        output_file.touch()  # Create the output file if it doesn't exist
    
    process_images_in_directory(Path("input/"), output_file)

    print(f"\nAll extracted text has been saved to {output_file}")
