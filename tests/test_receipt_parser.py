from services.receipt_parser import merge_drafts, parse_ocr


THAI_RECEIPT = """
ร้านตัวอย่าง มาร์เก็ต
เลขที่ใบเสร็จ 000123
วันที่ 19/10/2569 14:30
นมสด 2 x 15.00 30.00
ขนมปัง 25.50
VAT 7% 3.50
ยอดรวมสุทธิ 55.50
เงินสด 100.00
เงินทอน 44.50
ขอบคุณ
"""


def test_parse_ocr_prefills_receipt_fields_without_category():
    result = parse_ocr(THAI_RECEIPT)
    assert result == {
        "merchant": "ร้านตัวอย่าง มาร์เก็ต",
        "date": "2026-10-19",
        "items": [
            {"name": "นมสด", "quantity": "2", "line_total": "30.00", "category": None},
            {"name": "ขนมปัง", "quantity": "1", "line_total": "25.50", "category": None},
        ],
        "receipt_total": "55.50",
    }


def test_parse_ocr_accepts_thousands_and_comma_decimal():
    result = parse_ocr("SHOP\nRice 1,234.50\nWater 10,50\nTOTAL 1,245.00")
    assert [item["line_total"] for item in result["items"]] == ["1234.50", "10.50"]
    assert result["receipt_total"] == "1245.00"


def test_parse_ocr_sums_items_only_when_no_printed_total():
    result = parse_ocr("ร้าน กขค\nสินค้า A 10.00\nสินค้า B 20.50")
    assert result["receipt_total"] == "30.50"


def test_merge_uses_ocr_prices_and_ignores_ai_category():
    ocr = parse_ocr(THAI_RECEIPT)
    ai = {
        "merchant": "ชื่อที่ AI เดาผิด",
        "date": "2026-10-20",
        "receipt_total": "999.00",
        "items": [
            {"name": "นมสด", "quantity": None, "line_total": "999.00", "category": "ของใช้"},
            {"name": "ขนมปัง", "quantity": None, "line_total": "99.00", "category": "ของใช้"},
        ],
    }
    result = merge_drafts(ocr, ai)
    assert result["merchant"] == "ร้านตัวอย่าง มาร์เก็ต"
    assert result["date"] == "2026-10-19"
    assert result["receipt_total"] == "55.50"
    assert [item["line_total"] for item in result["items"]] == ["30.00", "25.50"]
    assert all(item["category"] is None for item in result["items"])


def test_merge_ai_fills_when_ocr_has_no_structured_items():
    result = merge_drafts(
        {"merchant": None, "date": None, "items": [], "receipt_total": None},
        {"merchant": "ร้าน AI", "date": "2026-10-19", "receipt_total": "10.00",
         "items": [{"name": "สินค้า", "quantity": None, "line_total": "10.00", "category": "ของใช้"}]},
    )
    assert result["merchant"] == "ร้าน AI"
    assert result["items"] == [{"name": "สินค้า", "quantity": "1", "line_total": "10.00", "category": None}]
