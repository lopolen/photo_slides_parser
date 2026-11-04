import cv2
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

img = cv2.imread("slide.jpg")
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
# збільшення + бінаризація часто суттєво покращують результат
gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

text = pytesseract.image_to_string(gray, lang="ukr+end", config="--psm 6")
print(text)
