import os
import re
from PIL import Image, ImageFilter, ImageOps
import pytesseract

Image.MAX_IMAGE_PIXELS = 20_000_000


def extract_text(path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((2400, 3200))
        if image.width < 1600:
            scale = min(2.5, 1600 / image.width)
            image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
        image = ImageOps.autocontrast(ImageOps.grayscale(image))
        image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))
        candidates = [pytesseract.image_to_string(image, lang="tha+eng", config=f"--psm {psm}", timeout=90).strip()
                      for psm in (6, 4)]
    def score(text):
        money_lines = sum(bool(re.search(r"\d[.,]\d{2}|\d+\.?-\s*$", line)) for line in text.splitlines())
        labels = sum(word in text.casefold() for word in ("total", "รวม", "จำนวน", "รายละเอียด", "ลูกค้า", "customer"))
        return money_lines * 4 + labels * 2 + min(len(text), 2000) / 1000
    return max(candidates, key=score)


def health():
    try:
        langs = pytesseract.get_languages(config="")
        return {"ready": {"tha", "eng"}.issubset(langs), "languages": langs}
    except (OSError, RuntimeError, pytesseract.TesseractNotFoundError):
        return {"ready": False, "languages": []}
