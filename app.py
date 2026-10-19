import io
import json
import os
import re
import secrets
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException
from services import database, llm, ocr, receipt_parser
from services.validation import CATEGORIES, ValidationError, validate_receipt

BASE = Path(__file__).resolve().parent


def now():
    return datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds")


def create_app(test_config=None):
    app = Flask(__name__, instance_path=os.environ.get("RECEIPT_INSTANCE", str(BASE / "instance")))
    app.config.update(MAX_CONTENT_LENGTH=10 * 1024 * 1024, LLAMA_URL=os.environ.get("LLAMA_URL", "http://127.0.0.1:8081"),
                      RUN_WORKER=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    if test_config:
        app.config.update(test_config)
    instance = Path(app.instance_path)
    instance.mkdir(parents=True, exist_ok=True)
    secret_file = instance / "session.key"
    try:
        with secret_file.open("x") as file:
            os.chmod(secret_file, 0o600)
            file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    app.secret_key = secret_file.read_text().strip()
    app.config.setdefault("DATABASE", str(instance / "receipts.db"))
    app.config["UPLOAD_DIR"] = instance / "uploads"
    app.config["UPLOAD_DIR"].mkdir(exist_ok=True)
    llm.endpoint(app.config["LLAMA_URL"])
    database.initialize(app.config["DATABASE"])
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="receipt") if app.config["RUN_WORKER"] else None
    app.extensions["analysis_executor"] = executor
    app.extensions["ocr_health"] = ocr.health()

    def db():
        return database.connect(app.config["DATABASE"])

    def get_receipt(receipt_id):
        with db() as conn:
            row = conn.execute("SELECT * FROM receipts WHERE id=?", (receipt_id,)).fetchone()
        if row is None:
            abort(404)
        return dict(row)

    @app.before_request
    def csrf():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(32)
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            if not secrets.compare_digest(token, session["csrf"]):
                abort(400, description="หน้าเว็บหมดอายุ กรุณาโหลดหน้าใหม่แล้วลองอีกครั้ง")

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def shared():
        return {"categories": CATEGORIES, "today": datetime.now(ZoneInfo("Asia/Bangkok")).date().isoformat()}

    @app.template_filter("baht")
    def baht(value):
        return f"{(value or 0) / 100:,.2f}"

    @app.get("/")
    def upload():
        with db() as conn:
            drafts = conn.execute("SELECT id,status,created_at FROM receipts WHERE status!='confirmed' ORDER BY created_at DESC LIMIT 20").fetchall()
        return render_template("upload.html", drafts=drafts)

    @app.get("/health")
    def health():
        with db() as conn:
            conn.execute("SELECT 1").fetchone()
        ai_ready = llm.health(app.config["LLAMA_URL"])
        return jsonify(web=True, database=True, ocr=app.extensions["ocr_health"], ai=ai_ready,
                       full_pipeline_ready=app.extensions["ocr_health"]["ready"] and ai_ready)

    @app.post("/analyze")
    def analyze_upload():
        uploaded = request.files.get("image")
        if not uploaded or not uploaded.filename:
            abort(400, description="กรุณาเลือกภาพ JPG หรือ PNG")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                raw = uploaded.read()
                with Image.open(io.BytesIO(raw)) as check:
                    if check.format not in {"JPEG", "PNG"}:
                        raise ValueError
                    check.verify()
                with Image.open(io.BytesIO(raw)) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    image.thumbnail((2400, 3200))
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            abort(400, description="ไฟล์ไม่ใช่ภาพ JPG/PNG ที่สมบูรณ์ หรือมีขนาดเกิน 20 ล้านพิกเซล")
        receipt_id = uuid4().hex
        image_name = receipt_id + ".jpg"
        image_path = app.config["UPLOAD_DIR"] / image_name
        image.save(image_path, "JPEG", quality=95)
        try:
            with db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                active = conn.execute("SELECT COUNT(*) FROM receipts WHERE status IN ('queued','processing')").fetchone()[0]
                if active >= 3:
                    abort(429, description="มีใบเสร็จรอวิเคราะห์อยู่ กรุณารอสักครู่")
                conn.execute("INSERT INTO receipts(id,image_name,status,created_at) VALUES(?,?,'queued',?)", (receipt_id, image_name, now()))
        except Exception:
            image_path.unlink(missing_ok=True)
            raise
        if executor:
            executor.submit(process, receipt_id)
        return redirect(url_for("review", receipt_id=receipt_id), code=303)

    def process(receipt_id):
        with app.app_context():
            with db() as conn:
                conn.execute("UPDATE receipts SET status='processing' WHERE id=?", (receipt_id,))
            record = get_receipt(receipt_id)
            text, result, error, source = "", {}, "", "manual"
            ocr_time, ai_time = None, None
            try:
                started = time.monotonic()
                text = ocr.extract_text(app.config["UPLOAD_DIR"] / record["image_name"])
                ocr_time = round(time.monotonic() - started, 3)
                with db() as conn:
                    conn.execute("UPDATE receipts SET ocr_text=?,ocr_seconds=? WHERE id=?", (text, ocr_time, receipt_id))
                if not text:
                    raise llm.AnalysisError("อ่านตัวอักษรไม่พบ ลองถ่ายภาพใหม่ในที่สว่าง หรือกรอกข้อมูลด้วยตนเอง")
                ocr_draft = receipt_parser.parse_ocr(text)
                result = ocr_draft
                source = "ocr_fallback"
                started = time.monotonic()
                ai_result = llm.analyze(text, app.config["LLAMA_URL"])
                ai_time = round(time.monotonic() - started, 3)
                result = receipt_parser.merge_drafts(ocr_draft, ai_result)
                source = "local_ai"
            except llm.AnalysisError as exc:
                if result.get("items") or result.get("receipt_total"):
                    error = f"{exc} ระบบกรอกข้อมูลที่อ่านได้จาก OCR ให้แล้ว โปรดเทียบกับภาพก่อนยืนยัน"
                else:
                    error = str(exc)
            except Exception:
                app.logger.exception("Receipt analysis failed: %s", receipt_id)
                error = "OCR ทำงานไม่สำเร็จ กรุณาตรวจภาพหรือตรวจการติดตั้งภาษาไทย และกรอกข้อมูลด้วยตนเอง"
            finally:
                with db() as conn:
                    conn.execute("UPDATE receipts SET status='review',ocr_text=?,draft_json=?,analysis_error=?,analysis_source=?,ocr_seconds=?,ai_seconds=? WHERE id=?",
                                 (text, json.dumps(result, ensure_ascii=False), error, source, ocr_time, ai_time, receipt_id))
    app.extensions["process_receipt"] = process

    @app.get("/review/<receipt_id>")
    def review(receipt_id):
        receipt = get_receipt(receipt_id)
        if receipt["status"] == "confirmed":
            return redirect(url_for("detail", receipt_id=receipt_id))
        return render_template("review.html", receipt=receipt, draft=json.loads(receipt["draft_json"]))

    @app.get("/api/receipts/<receipt_id>/status")
    def receipt_status(receipt_id):
        receipt = get_receipt(receipt_id)
        return jsonify(status=receipt["status"])

    @app.get("/receipts/<receipt_id>/image")
    def receipt_image(receipt_id):
        receipt = get_receipt(receipt_id)
        return send_file(app.config["UPLOAD_DIR"] / receipt["image_name"], mimetype="image/jpeg")

    @app.post("/receipts/<receipt_id>/confirm")
    def confirm(receipt_id):
        record = get_receipt(receipt_id)
        if record["status"] == "confirmed":
            return jsonify(url=url_for("detail", receipt_id=receipt_id))
        if record["status"] != "review":
            abort(409, description="กรุณารอการวิเคราะห์ให้เสร็จก่อน")
        try:
            clean = validate_receipt(request.get_json(silent=True))
        except ValidationError as exc:
            return jsonify(error=str(exc)), 422
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT status FROM receipts WHERE id=?", (receipt_id,)).fetchone()[0]
            if current == "confirmed":
                return jsonify(url=url_for("detail", receipt_id=receipt_id))
            conn.execute("UPDATE receipts SET status='confirmed',confirmed_at=?,merchant=?,purchased_on=?,total_cents=?,adjustment_cents=?,adjustment_note=?,difference_cents=? WHERE id=?",
                         (now(), clean["merchant"], clean["purchased_on"], clean["total_cents"], clean["adjustment_cents"], clean["adjustment_note"], clean["difference_cents"], receipt_id))
            conn.executemany("INSERT INTO receipt_items(receipt_id,name,quantity,line_cents,category) VALUES(?,?,?,?,?)",
                             [(receipt_id, i["name"], i["quantity"], i["line_cents"], i["category"]) for i in clean["items"]])
        return jsonify(url=url_for("detail", receipt_id=receipt_id))

    def summary(month):
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            abort(400, description="เดือนที่เลือกไม่ถูกต้อง")
        with db() as conn:
            records = [dict(r) for r in conn.execute("SELECT * FROM receipts WHERE status='confirmed' AND substr(purchased_on,1,7)=? ORDER BY purchased_on DESC,created_at DESC", (month,))]
            grouped = [dict(r) for r in conn.execute("SELECT i.category,SUM(i.line_cents) AS amount FROM receipt_items i JOIN receipts r ON i.receipt_id=r.id WHERE r.status='confirmed' AND substr(r.purchased_on,1,7)=? GROUP BY i.category ORDER BY amount DESC", (month,))]
        adjustment = sum(r["adjustment_cents"] for r in records)
        difference = sum(r["difference_cents"] for r in records)
        if adjustment:
            grouped.append({"category": "ส่วนลด / ค่าบริการ", "amount": adjustment})
        if difference:
            grouped.append({"category": "ส่วนต่างที่ตรวจยืนยัน", "amount": difference})
        return {"receipts": records, "categories": grouped, "total_cents": sum(r["total_cents"] for r in records), "count": len(records), "month": month}

    @app.get("/dashboard")
    def dashboard():
        month = request.args.get("month", now()[:7])
        data = summary(month)
        return render_template("dashboard.html", **data)

    @app.get("/api/summary")
    def api_summary():
        data = summary(request.args.get("month", now()[:7]))
        return jsonify({k: v for k, v in data.items() if k != "receipts"})

    @app.get("/receipts/<receipt_id>")
    def detail(receipt_id):
        receipt = get_receipt(receipt_id)
        if receipt["status"] != "confirmed":
            return redirect(url_for("review", receipt_id=receipt_id))
        with db() as conn:
            items = conn.execute("SELECT * FROM receipt_items WHERE receipt_id=? ORDER BY id", (receipt_id,)).fetchall()
        return render_template("detail.html", receipt=receipt, items=items)

    @app.errorhandler(HTTPException)
    def error(exc):
        messages = {404: "ไม่พบรายการที่ต้องการ", 413: "ภาพมีขนาดเกิน 10 MB กรุณาเลือกภาพที่เล็กลง"}
        message = messages.get(exc.code, exc.description)
        if request.is_json or request.path.startswith("/api/"):
            return jsonify(error=message), exc.code
        return render_template("error.html", message=message, code=exc.code), exc.code

    return app


if __name__ == "__main__":
    from waitress import serve
    serve(create_app(), host=os.environ.get("APP_HOST", "127.0.0.1"), port=int(os.environ.get("APP_PORT", "5000")), threads=4)
