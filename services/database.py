import sqlite3
from pathlib import Path


def connect(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS receipts (
            id TEXT PRIMARY KEY, image_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','processing','review','confirmed')),
            created_at TEXT NOT NULL, confirmed_at TEXT, merchant TEXT,
            purchased_on TEXT, total_cents INTEGER, adjustment_cents INTEGER NOT NULL DEFAULT 0,
            adjustment_note TEXT NOT NULL DEFAULT '', difference_cents INTEGER NOT NULL DEFAULT 0,
            ocr_text TEXT NOT NULL DEFAULT '', draft_json TEXT NOT NULL DEFAULT '{}',
            analysis_source TEXT NOT NULL DEFAULT 'pending', analysis_error TEXT NOT NULL DEFAULT '',
            ocr_seconds REAL, ai_seconds REAL
        );
        CREATE TABLE IF NOT EXISTS receipt_items (
            id INTEGER PRIMARY KEY, receipt_id TEXT NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
            name TEXT NOT NULL, quantity TEXT NOT NULL, line_cents INTEGER NOT NULL CHECK(line_cents >= 0),
            category TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS receipt_date_idx ON receipts(status,purchased_on);
        """)
        # One web process owns the worker. A previous process cannot resume its in-memory jobs.
        db.execute("UPDATE receipts SET status='review', analysis_source='manual', analysis_error=? WHERE status IN ('queued','processing')",
                   ("ระบบเริ่มใหม่ระหว่างวิเคราะห์ กรุณาตรวจและกรอกข้อมูล หรืออัปโหลดภาพใหม่",))
