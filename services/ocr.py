import os
from PIL import Image, ImageOps
import pytesseract

Image.MAX_IMAGE_PIXELS = 20_000_000


def extract_text(path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((2400, 3200))
        image = ImageOps.autocontrast(ImageOps.grayscale(image))
        text = pytesseract.image_to_string(image, lang="tha+eng", config="--psm 6", timeout=90)
    return text.strip()


def health():
    try:
        langs = pytesseract.get_languages(config="")
        return {"ready": {"tha", "eng"}.issubset(langs), "languages": langs}
    except (OSError, RuntimeError, pytesseract.TesseractNotFoundError):
        return {"ready": False, "languages": []}
