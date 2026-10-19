import io
import json
from datetime import datetime
from uuid import uuid4
import pytest
from PIL import Image
from app import create_app
from services import database


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('RECEIPT_INSTANCE', str(tmp_path / 'instance'))
    app = create_app({'TESTING': True, 'RUN_WORKER': False})
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf']


@pytest.fixture
def receipt(app):
    receipt_id = uuid4().hex
    Image.new('RGB',(100,100),'white').save(app.config['UPLOAD_DIR'] / (receipt_id + '.jpg'))
    with database.connect(app.config['DATABASE']) as db:
        db.execute("INSERT INTO receipts(id,image_name,status,created_at) VALUES(?,?,'review',?)", (receipt_id,receipt_id+'.jpg',datetime.now().isoformat()))
    return receipt_id


@pytest.fixture
def payload():
    return {'merchant':'ร้านทดสอบ','date':'2026-10-19','receipt_total':'45.50','adjustment':'0','items':[
        {'name':'ขนมปัง','quantity':'1','line_total':'15.50','category':'อาหารและเครื่องดื่ม'},
        {'name':'นม','quantity':'2','line_total':'30.00','category':'อาหารและเครื่องดื่ม'}]}
