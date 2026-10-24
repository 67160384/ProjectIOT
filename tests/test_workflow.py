import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import pytest
from app import create_app
from services import database, llm, ocr
from services.validation import validate_receipt, ValidationError


def post(client, csrf, receipt, payload):
    return client.post(f'/receipts/{receipt}/confirm',json=payload,headers={'X-CSRF-Token':csrf})


def test_confirm_persist_dashboard_and_idempotence(app,client,csrf,receipt,payload):
    assert client.get('/api/summary?month=2026-10').json['count'] == 0
    response=post(client,csrf,receipt,payload)
    assert response.status_code == 200
    assert post(client,csrf,receipt,payload).status_code == 200
    assert client.get(response.json['url']).status_code == 200
    summary=client.get('/api/summary?month=2026-10').json
    assert summary['total_cents']==4550 and summary['count']==1
    assert sum(c['amount'] for c in summary['categories'])==4550
    assert client.get('/api/summary?month=2026-11').json['count']==0
    restarted=create_app({'TESTING':True,'RUN_WORKER':False})
    assert restarted.test_client().get('/api/summary?month=2026-10').json['total_cents']==4550
    with database.connect(app.config['DATABASE']) as db:
        assert db.execute('SELECT count(*) FROM receipt_items').fetchone()[0]==2


def test_mismatch_requires_explicit_ack_and_chart_balances(client,csrf,receipt,payload):
    payload['receipt_total']='40.00'
    assert post(client,csrf,receipt,payload).status_code==422
    payload['acknowledge_mismatch']='true'
    assert post(client,csrf,receipt,payload).status_code==422
    payload['acknowledge_mismatch']=True
    assert post(client,csrf,receipt,payload).status_code==200
    data=client.get('/api/summary?month=2026-10').json
    assert sum(c['amount'] for c in data['categories'])==4000
    assert data['categories'][-1]['amount']==-550


def test_discount_requires_note_and_correct_math(client,csrf,receipt,payload):
    payload.update(receipt_total='35.50',adjustment='-10.00')
    assert post(client,csrf,receipt,payload).status_code==422
    payload['adjustment_note']='ส่วนลดสมาชิก'
    assert post(client,csrf,receipt,payload).status_code==200
    data=client.get('/api/summary?month=2026-10').json
    assert data['total_cents']==3550
    assert sum(c['amount'] for c in data['categories'])==3550


def test_positive_discount_field_is_subtracted(client,csrf,receipt,payload):
    payload.pop('adjustment')
    payload.update(receipt_total='39.50',discount='6.00',adjustment_note='ส่วนลดสมาชิก')
    assert post(client,csrf,receipt,payload).status_code==200
    data=client.get('/api/summary?month=2026-10').json
    assert data['total_cents']==3950
    assert sum(c['amount'] for c in data['categories'])==3950
    assert data['categories'][-1]=={'category':'ส่วนลด / ค่าบริการ','amount':-600}


def test_negative_discount_field_rejected(client,csrf,receipt,payload):
    payload.pop('adjustment')
    payload.update(receipt_total='45.50',discount='-6.00',adjustment_note='ส่วนลด')
    assert post(client,csrf,receipt,payload).status_code==422


def test_custom_category_is_saved_and_grouped(client,csrf,receipt,payload):
    payload['items'][0]['category']='บริการล้างแอร์'
    payload['items'][1]['category']='บริการล้างแอร์'
    assert post(client,csrf,receipt,payload).status_code==200
    data=client.get('/api/summary?month=2026-10').json
    assert data['categories']==[{'category':'บริการล้างแอร์','amount':4550}]


def test_invalid_custom_category_rejected(client,csrf,receipt,payload):
    payload['items'][0]['category']='x'*51
    assert post(client,csrf,receipt,payload).status_code==422


@pytest.mark.parametrize('bad',['NaN','Infinity','-1','1.999','abc',None,'10000001'])
def test_invalid_money_rejected(payload,bad):
    payload['items'][0]['line_total']=bad
    with pytest.raises(ValidationError):validate_receipt(payload)


@pytest.mark.parametrize('bad',['0','-1','NaN','Infinity','1.0001','10001'])
def test_invalid_quantity_rejected(payload,bad):
    payload['items'][0]['quantity']=bad
    with pytest.raises(ValidationError):validate_receipt(payload)


def test_decimal_exactness(payload):
    payload['items'][0]['line_total']='0.10'
    payload['items'][1]['line_total']='0.20'
    payload['receipt_total']='0.30'
    assert validate_receipt(payload)['difference_cents']==0


def test_required_fields_and_date(payload):
    for field,value in [('date','2026-02-30'),('merchant',''),('items',[])]:
        data={**payload,field:value}
        with pytest.raises(ValidationError):validate_receipt(data)


def image_bytes(fmt='PNG'):
    image=io.BytesIO()
    Image.new('RGB',(320,300),'white').save(image,fmt)
    image.seek(0)
    return image


@pytest.mark.parametrize('fmt',['JPEG','PNG'])
def test_image_upload_is_verified_normalized_and_queued(client,csrf,app,fmt):
    result=client.post('/analyze',data={'csrf_token':csrf,'image':(image_bytes(fmt),'../../outside.jpg')})
    assert result.status_code==303
    assert client.get(result.location).status_code==200
    with database.connect(app.config['DATABASE']) as db:
        row=db.execute('SELECT * FROM receipts').fetchone()
    assert row['status']=='queued'
    assert '/' not in row['image_name']
    assert (app.config['UPLOAD_DIR']/row['image_name']).exists()


def test_fake_image_rejected(client,csrf):
    result=client.post('/analyze',data={'csrf_token':csrf,'image':(io.BytesIO(b'<script>alert(1)</script>'),'a.png')})
    assert result.status_code==400


def test_oversize_request_rejected(client,csrf):
    result=client.post('/analyze',data={'csrf_token':csrf,'image':(io.BytesIO(b'a'*(10*1024*1024)),'a.png')})
    assert result.status_code==413


def test_queue_limit_and_cleanup(client,csrf,app):
    for _ in range(3):
        assert client.post('/analyze',data={'csrf_token':csrf,'image':(image_bytes(),'a.png')}).status_code==303
    assert client.post('/analyze',data={'csrf_token':csrf,'image':(image_bytes(),'a.png')}).status_code==429
    assert len(list(app.config['UPLOAD_DIR'].glob('*.jpg')))==3


def test_csrf_and_escaping(client,csrf,receipt,payload):
    assert client.post(f'/receipts/{receipt}/confirm',json=payload).status_code==400
    payload['merchant']='<script>alert(1)</script>'
    assert post(client,csrf,receipt,payload).status_code==200
    response=client.get(f'/receipts/{receipt}')
    assert b'<script>alert(1)</script>' not in response.data
    assert b'&lt;script&gt;' in response.data
    assert "default-src 'self'" in response.headers['Content-Security-Policy']


def test_ocr_survives_ai_failure_and_manual_workflow(app,client,csrf,receipt,payload,monkeypatch):
    monkeypatch.setattr(ocr,'extract_text',lambda _: 'Test Shop\nMilk 30.00\nTOTAL 30.00')
    def unavailable(*args,**kwargs):raise llm.AnalysisError('AI unavailable')
    monkeypatch.setattr(llm,'analyze',unavailable)
    app.extensions['process_receipt'](receipt)
    with database.connect(app.config['DATABASE']) as db:
        row=db.execute('SELECT * FROM receipts WHERE id=?',(receipt,)).fetchone()
    assert 'Milk 30.00' in row['ocr_text'] and row['status']=='review'
    assert row['analysis_source']=='ocr_fallback' and 'AI unavailable' in row['analysis_error']
    draft=json.loads(row['draft_json'])
    assert draft['merchant']=='Test Shop'
    assert draft['items']==[{'name':'Milk','quantity':'1','line_total':'30.00','category':None}]
    assert post(client,csrf,receipt,payload).status_code==200


def test_ai_orchestration_with_stub_not_model_accuracy(app,receipt,payload,monkeypatch):
    monkeypatch.setattr(ocr,'extract_text',lambda _: 'Milk 30.00')
    monkeypatch.setattr(llm,'analyze',lambda *args:payload)
    app.extensions['process_receipt'](receipt)
    with database.connect(app.config['DATABASE']) as db:
        row=db.execute('SELECT * FROM receipts WHERE id=?',(receipt,)).fetchone()
    assert row['analysis_source']=='local_ai' and row['status']=='review'
    assert json.loads(row['draft_json'])['merchant']==payload['merchant']


def test_recovery_after_interrupted_process(app,client,csrf):
    response=client.post('/analyze',data={'csrf_token':csrf,'image':(image_bytes(),'a.png')})
    fresh=create_app({'TESTING':True,'RUN_WORKER':False})
    with database.connect(fresh.config['DATABASE']) as db:
        row=db.execute('SELECT * FROM receipts').fetchone()
    assert row['status']=='review' and 'ระบบเริ่มใหม่' in row['analysis_error']


def test_concurrent_confirmation_is_atomic(app,receipt,payload):
    def submit(_):
        client=app.test_client();client.get('/')
        with client.session_transaction() as session:token=session['csrf']
        return post(client,token,receipt,payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(submit,range(2)))==[200,200]
    with database.connect(app.config['DATABASE']) as db:
        assert db.execute('SELECT count(*) FROM receipt_items').fetchone()[0]==2


@pytest.mark.parametrize('url',['https://api.example.com','http://127.0.0.1.evil.test:8081','http://user:pass@localhost','http://localhost/x'])
def test_external_llm_urls_rejected(url):
    with pytest.raises(ValueError):llm.endpoint(url)


def test_month_validation_and_missing_receipt(client):
    assert client.get('/dashboard?month=2026-13').status_code==400
    assert client.get('/receipts/missing').status_code==404


def test_overlong_ocr_is_not_silently_truncated():
    with pytest.raises(llm.AnalysisError):llm.analyze('a'*2401,'http://localhost:8081')
