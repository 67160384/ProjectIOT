import json
from pathlib import Path
import pytest
from services import llm, ocr


def test_real_thai_english_ocr_fixture():
    assert ocr.health()['ready'], 'Install Tesseract tha and eng before running the integration check'
    text=ocr.extract_text(Path(__file__).parent/'fixtures/synthetic_receipt.png')
    assert 'ร้านทดสอบ' in text and 'ขนมปัง' in text
    assert '15.50' in text and '30.00' in text and '45.50' in text


class FakeResponse:
    def __init__(self, content, finish):self.content,self.finish=content,finish
    def raise_for_status(self):pass
    def json(self):return {'choices':[{'finish_reason':self.finish,'message':{'content':self.content}}]}


@pytest.mark.parametrize('content,finish',[('{"items":[]}','length'),('not json','stop'),('{"items":[1]}','stop'),('[]','stop')])
def test_reject_invalid_or_incomplete_llm_responses(monkeypatch,content,finish):
    class FakeSession:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,*args,**kwargs):return FakeResponse(content,finish)
    monkeypatch.setattr(llm,'session',FakeSession)
    with pytest.raises(llm.AnalysisError):llm.analyze('TOTAL 45.50','http://localhost:8081')


def test_llm_request_contract_and_no_proxy(monkeypatch):
    real_session=llm.session()
    assert real_session.trust_env is False
    real_session.close()
    result={'merchant':'ร้าน','date':None,'items':[],'receipt_total':'45.50'}
    class FakeSession:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            assert url=='http://127.0.0.1:8081/v1/chat/completions'
            payload=kwargs['json']
            assert payload['response_format']['json_schema']['schema']==llm.SCHEMA
            assert payload['temperature']==0 and payload['stream'] is False
            return FakeResponse(json.dumps(result),'stop')
    monkeypatch.setattr(llm,'session',FakeSession)
    assert llm.analyze('TOTAL 45.50','http://127.0.0.1:8081')==result
