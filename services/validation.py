"""Validate human-reviewed data; money never passes through binary float."""
from datetime import date
from decimal import Decimal, InvalidOperation

CATEGORIES = ("อาหารและเครื่องดื่ม", "ของใช้", "เดินทาง", "สุขภาพ", "อื่น ๆ")


class ValidationError(ValueError):
    pass


def cents(value, label="ยอดเงิน", signed=False):
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or abs(amount) > 10_000_000:
            raise ValueError
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError
        if not signed and amount < 0:
            raise ValueError
        return int(amount * 100)
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(f"{label}: ต้องเป็นจำนวนเงินที่ถูกต้อง ทศนิยมไม่เกิน 2 ตำแหน่ง") from None


def validate_receipt(data):
    if not isinstance(data, dict):
        raise ValidationError("ข้อมูลใบเสร็จไม่ถูกต้อง")
    merchant = str(data.get("merchant") or "").strip()
    if not merchant or len(merchant) > 120:
        raise ValidationError("กรุณาระบุชื่อร้านหรือชื่อลูกค้า ไม่เกิน 120 ตัวอักษร")
    purchased = data.get("date")
    try:
        if not isinstance(purchased, str) or date.fromisoformat(purchased).isoformat() != purchased:
            raise ValueError
    except ValueError:
        raise ValidationError("กรุณาตรวจวันที่ซื้อให้ถูกต้อง (ปี ค.ศ.)") from None
    source = data.get("items")
    if not isinstance(source, list) or not 1 <= len(source) <= 100:
        raise ValidationError("ต้องมีสินค้า 1–100 รายการ")
    items = []
    for index, item in enumerate(source, 1):
        if not isinstance(item, dict):
            raise ValidationError("ข้อมูลสินค้าไม่ถูกต้อง")
        name = str(item.get("name") or "").strip()
        if not name or len(name) > 150:
            raise ValidationError(f"รายการที่ {index}: กรุณาระบุชื่อสินค้า ไม่เกิน 150 ตัวอักษร")
        try:
            quantity = Decimal(str(item.get("quantity", "1")))
            if not quantity.is_finite() or not 0 < quantity <= 10000 or quantity != quantity.quantize(Decimal("0.001")):
                raise ValueError
        except (InvalidOperation, ValueError):
            raise ValidationError(f"รายการที่ {index}: จำนวนต้องมากกว่า 0 และทศนิยมไม่เกิน 3 ตำแหน่ง") from None
        category = str(item.get("category") or "").strip()
        if not category or len(category) > 50 or any(ord(character) < 32 for character in category):
            raise ValidationError(f"รายการที่ {index}: กรุณาเลือกหรือพิมพ์หมวดหมู่ ไม่เกิน 50 ตัวอักษร")
        items.append({"name": name, "quantity": str(quantity), "line_cents": cents(item.get("line_total"), f"รายการที่ {index}"), "category": category})
    total = cents(data.get("receipt_total"))
    if "discount" in data:
        adjustment = -cents(data.get("discount", "0"), "ส่วนลด")
    else:
        # Compatibility with drafts/tests created before the dedicated discount field.
        adjustment = cents(data.get("adjustment", "0"), "ส่วนลด/ค่าบริการ", signed=True)
    adjustment_note = str(data.get("adjustment_note") or "").strip()
    if len(adjustment_note) > 200 or (adjustment and not adjustment_note):
        raise ValidationError("กรุณาระบุเหตุผลส่วนลด ไม่เกิน 200 ตัวอักษร")
    expected = sum(i["line_cents"] for i in items) + adjustment
    difference = total - expected
    if difference and data.get("acknowledge_mismatch") is not True:
        raise ValidationError(f"ยอดต่างกัน {difference / 100:,.2f} บาท กรุณาแก้ไขหรือยืนยันว่าตรวจสอบส่วนต่างแล้ว")
    return {"merchant": merchant, "purchased_on": purchased, "total_cents": total, "adjustment_cents": adjustment,
            "adjustment_note": adjustment_note, "difference_cents": difference, "items": items}
