"""Real browser + real OCR. Manual review is intentional; this does not prove AI accuracy."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:5000')
parser.add_argument('--output',default='docs/evidence')
parser.add_argument('--require-ai',action='store_true',help='Fail unless actual local AI analysis completes')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    context=browser.new_context(viewport={'width':1440,'height':1060},device_scale_factor=1)
    external=[];errors=[]
    def route(request):
        if urlsplit(request.request.url).hostname not in {'127.0.0.1','localhost'}:
            external.append(request.request.url);request.abort()
        else:request.continue_()
    context.route('**/*',route)
    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(args.url);page.evaluate('document.fonts.ready');page.wait_for_timeout(500)
    page.screenshot(path=str(out/'01-upload.png'),full_page=True)
    health=page.request.get(args.url+'/health').json()
    if args.require_ai:assert health['full_pipeline_ready'], 'Local AI or OCR is not ready'
    page.locator('#image').set_input_files(str(root/'tests/fixtures/synthetic_receipt.png'))
    page.locator('#analyze-button').click()
    page.wait_for_selector('#review-form',timeout=240000)
    ai_ran=page.locator('.receipt-view .pill').inner_text()=='AI + OCR ในเครื่อง'
    if args.require_ai:assert ai_ran, 'Receipt fell back to manual review; actual AI did not complete'
    assert '45.50' in page.locator('.ocr-text').text_content()
    raw_draft={'merchant':page.locator('[name="merchant"]').input_value(),
               'receipt_total':page.locator('[name="receipt_total"]').input_value(),
               'items':page.locator('.item-row').evaluate_all('(rows) => rows.map(row => Object.fromEntries([...row.querySelectorAll("[data-field]")].map(el => [el.dataset.field, el.value])))')}
    assert all(item['category'] == '' for item in raw_draft['items']), 'Categories must be selected by the user'
    if ai_ran:page.screenshot(path=str(out/'08-ai-before-review.png'),full_page=True)
    page.locator('[name="merchant"]').fill('ร้านทดสอบ · ข้อมูลสาธิต')
    page.locator('[name="date"]').fill('2026-10-19')
    while page.locator('.item-row').count()>0:page.locator('.remove-item').first.click()
    for name,qty,amount in [('ขนมปัง','1','15.50'),('นม','2','30.00')]:
        page.locator('#add-item').click();row=page.locator('.item-row').last
        row.locator('[data-field="name"]').fill(name)
        row.locator('[data-field="quantity"]').fill(qty)
        row.locator('[data-field="line_total"]').fill(amount)
        row.locator('[data-field="category"]').fill('อาหารและเครื่องดื่ม')
    page.locator('[name="discount"]').fill('6.00')
    page.locator('[name="receipt_total"]').fill('39.50')
    assert '39.50' in page.locator('#calculated-total').inner_text(), 'Positive discount must be subtracted'
    page.locator('[name="discount"]').fill('0')
    page.locator('[name="receipt_total"]').fill('45.50')
    page.screenshot(path=str(out/'02-review.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.locator('.total-box').scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    page.screenshot(path=str(out/'06-review-mobile.png'))
    page.set_viewport_size({'width':1440,'height':1060})
    page.locator('#save-button').click();page.wait_for_url('**/receipts/*')
    assert '45.50' in page.locator('.saved-total').inner_text()
    page.goto(args.url+'/dashboard?month=2026-10')
    page.wait_for_selector('#expense-chart');page.wait_for_timeout(700)
    page.screenshot(path=str(out/'03-dashboard.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(700)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
    page.screenshot(path=str(out/'04-mobile.png'),full_page=True)
    page.screenshot(path=str(out/'07-dashboard-mobile.png'))
    page.goto(args.url);page.wait_for_timeout(300)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Upload mobile overflow'
    page.locator('#upload-form').screenshot(path=str(out/'05-upload-mobile.png'))
    assert not external, external
    assert not errors, errors
    evidence={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'fixture':'synthetic_receipt.png (generated, not a real receipt)',
              'checks':['real Thai/English Tesseract OCR','upload → manual correction → confirm → dashboard','mobile layout at 390px','frontend loads with all external requests blocked'],
              'health':health,'actual_local_ai_completed':ai_ran,'draft_before_human_correction':raw_draft,'external_browser_requests':external,'javascript_errors':errors,
              'limitations':['No physical Raspberry Pi tested','No claim of model inference accuracy','Browser egress blocking is not a physical disconnected-Pi test']}
    (out/'browser-results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps(evidence,ensure_ascii=False,indent=2))
    browser.close()
