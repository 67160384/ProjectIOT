"""Conservative OCR parser and merger for an editable receipt draft.

The parser only uses values printed in OCR text. It never confirms a receipt;
the user must still compare the draft with the source image.
"""
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

MONEY_AT_END = re.compile(
    r"(?P<amount>-?(?:\d{1,3}(?:,\d{3})+|\d{1,8})(?:[.,]\d{2}|\.?-))\s*(?:บาท|฿)?\s*$",
    re.IGNORECASE,
)
DATE_PATTERNS = (
    re.compile(r"(?<!\d)(?P<year>20\d{2}|25\d{2})[-/.](?P<month>0?[1-9]|1[0-2])[-/.](?P<day>0?[1-9]|[12]\d|3[01])(?!\d)"),
    re.compile(r"(?<!\d)(?P<day>0?[1-9]|[12]\d|3[01])[-/.](?P<month>0?[1-9]|1[0-2])[-/.](?P<year>20\d{2}|25\d{2})(?!\d)"),
)

TOTAL_WORDS = (
    "grand total", "net total", "amount due", "ยอดสุทธิ", "ยอดรวมสุทธิ",
    "รวมทั้งสิ้น", "ยอดชำระ", "รวมเงิน", "รวม", "total",
)
NON_ITEM_WORDS = (
    *TOTAL_WORDS, "subtotal", "sub total", "ยอดก่อนภาษี", "vat", "tax", "ภาษี",
    "cash", "เงินสด", "change", "เงินทอน", "discount", "ส่วนลด", "payment",
    "ชำระ", "balance", "tender", "credit", "debit", "เลขที่ใบเสร็จ", "receipt no",
    "โทร", "tel", "โทรศัพท์", "date", "วันที่", "time", "เวลา",
)
MERCHANT_NOISE = (
    "receipt", "ใบเสร็จ", "tax invoice", "ใบกำกับภาษี", "thank", "ขอบคุณ",
    "date", "วันที่", "tel", "โทร", "เลขที่", "สาขา", "branch",
)
CUSTOMER_PATTERN = re.compile(
    r"(?:ลูกค้า|customer)\s*[:：]?\s*(?P<name>.+?)"
    r"(?=\s+(?:เลขที่|เลขประจำตัว|เลขผู้เสียภาษี|ที่อยู่|address|ผู้ติดต่อ|เบอร์|โทร|tel|วันที่|date|no\.?|id)\s*[:：]?|$)",
    re.IGNORECASE,
)


def _clean_line(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip(" |:;_")


def _money(value):
    if value is None:
        return None
    text = str(value).strip().replace("฿", "").replace("บาท", "").replace(" ", "")
    if re.fullmatch(r"-?\d{1,8}(?:\.-|-)", text):
        text = text.rstrip("-").rstrip(".") + ".00"
    if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+\.\d{2}", text):
        text = text.replace(",", "")
    elif re.fullmatch(r"-?\d+[,]\d{2}", text):
        text = text.replace(",", ".")
    if not re.fullmatch(r"-?\d{1,8}\.\d{2}", text):
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0 or amount > Decimal("10000000"):
        return None
    return f"{amount:.2f}"


def _contains(line, words):
    lowered = line.casefold()
    return any(word in lowered for word in words)


def _date_from_text(text):
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        year = int(match.group("year"))
        if year >= 2400:
            year -= 543
        try:
            return date(year, int(match.group("month")), int(match.group("day"))).isoformat()
        except ValueError:
            continue
    return None


def _merchant(lines, first_item_index):
    for line in lines:
        match = CUSTOMER_PATTERN.search(line)
        if match:
            name = _clean_line(match.group("name"))
            name = re.split(r"\s+(?:เลขที่|เลขประจำตัว|เลขผู้เสียภาษี|no\.?|id)\s*[:：]?", name, maxsplit=1, flags=re.IGNORECASE)[0]
            if 1 < len(name) <= 120 and sum(character.isalpha() for character in name) >= 2:
                return name
    limit = first_item_index if first_item_index is not None else min(len(lines), 8)
    for line in lines[:limit]:
        if len(line) < 2 or len(line) > 120 or MONEY_AT_END.search(line):
            continue
        if _contains(line, MERCHANT_NOISE) or _date_from_text(line):
            continue
        if sum(character.isalpha() for character in line) < 2:
            continue
        return line
    return None


def parse_ocr(text):
    """Return an editable draft using only visible OCR lines."""
    lines = [_clean_line(line) for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    customer_name = _merchant(lines, None)
    items = []
    total_candidates = []
    first_item_index = None

    for index, line in enumerate(lines):
        match = MONEY_AT_END.search(line)
        if not match:
            continue
        amount = _money(match.group("amount"))
        if amount is None:
            continue
        prefix = _clean_line(line[:match.start()])
        lowered = prefix.casefold()
        if _contains(prefix, TOTAL_WORDS):
            score = next((len(TOTAL_WORDS) - rank for rank, word in enumerate(TOTAL_WORDS) if word in lowered), 0)
            total_candidates.append((score, index, amount))
            continue
        if not prefix or _contains(prefix, NON_ITEM_WORDS) or _date_from_text(prefix):
            continue
        if sum(character.isalpha() for character in prefix) < 1:
            continue

        quantity = "1"
        quantity_match = re.search(r"(?:^|\s)(\d+(?:\.\d{1,3})?)\s*[xX×]\s*\d+[.,]\d{2}\s*$", prefix)
        if quantity_match:
            quantity = quantity_match.group(1)
            prefix = _clean_line(prefix[:quantity_match.start()])
        else:
            # Table receipts commonly end a row with: description | quantity | unit price | line total.
            table_match = re.search(
                r"\s+(?P<quantity>\d+(?:[.,]\d{1,3})?)\s+"
                r"(?P<unit>(?:\d{1,3}(?:,\d{3})+|\d{1,8})(?:[.,]\d{2}|\.?-)?)(?:\s+[-–—])?\s*$",
                prefix,
            )
            if table_match:
                quantity = table_match.group("quantity").replace(",", ".")
                prefix = _clean_line(prefix[:table_match.start()])
        prefix = re.sub(r"^\d{1,3}\s+", "", prefix).strip()
        if customer_name and _name_key(prefix) == _name_key(customer_name):
            continue
        if not prefix:
            continue
        if first_item_index is None:
            first_item_index = index
        items.append({"name": prefix[:120], "quantity": quantity, "line_total": amount, "category": None})
        if len(items) >= 40:
            break

    receipt_total = None
    if total_candidates:
        receipt_total = max(total_candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]
    elif items:
        receipt_total = f"{sum(Decimal(item['line_total']) for item in items):.2f}"

    return {
        "merchant": customer_name or _merchant(lines, first_item_index),
        "date": _date_from_text("\n".join(lines)),
        "items": items,
        "receipt_total": receipt_total,
    }


def _name_key(value):
    return re.sub(r"[^0-9a-zก-๙]", "", str(value or "").casefold())


def _normalize_ai(result):
    if not isinstance(result, dict):
        return {"merchant": None, "date": None, "items": [], "receipt_total": None}
    items = []
    for item in result.get("items") if isinstance(result.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean_line(str(item.get("name") or ""))[:120]
        amount = _money(item.get("line_total"))
        if not name or amount is None:
            continue
        quantity = item.get("quantity")
        try:
            quantity = str(Decimal(str(quantity))) if quantity is not None and Decimal(str(quantity)) > 0 else "1"
        except (InvalidOperation, ValueError):
            quantity = "1"
        items.append({"name": name, "quantity": quantity, "line_total": amount, "category": None})
    merchant = _clean_line(str(result.get("merchant") or ""))[:120] or None
    return {"merchant": merchant, "date": _date_from_text(str(result.get("date") or "")),
            "items": items[:40], "receipt_total": _money(result.get("receipt_total"))}


def merge_drafts(ocr_draft, ai_result):
    """Keep OCR-line amounts when available; use AI to enrich missing fields/categories."""
    ai = _normalize_ai(ai_result)
    merged_items = []
    if ocr_draft.get("items"):
        for item in ocr_draft["items"]:
            key = _name_key(item["name"])
            match = next((candidate for candidate in ai["items"] if key and
                          (key in _name_key(candidate["name"]) or _name_key(candidate["name"]) in key)), None)
            merged = dict(item)
            if match:
                if merged["quantity"] == "1" and match["quantity"] != "1":
                    merged["quantity"] = match["quantity"]
            merged_items.append(merged)
    else:
        merged_items = ai["items"]

    return {
        "merchant": ocr_draft.get("merchant") or ai["merchant"],
        "date": ocr_draft.get("date") or ai["date"],
        "items": merged_items,
        "receipt_total": ocr_draft.get("receipt_total") or ai["receipt_total"],
    }
