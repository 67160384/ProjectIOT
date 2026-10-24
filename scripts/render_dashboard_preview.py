"""Render the standalone slide preview to PNG with the system Chromium."""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "dashboard-preview.png"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path="/usr/bin/chromium",
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.set_content((ROOT / "dashboard-preview.html").read_text(), wait_until="load")
    page.evaluate("document.fonts.ready")
    page.screenshot(path=str(OUTPUT), full_page=True)
    browser.close()

print(OUTPUT)
