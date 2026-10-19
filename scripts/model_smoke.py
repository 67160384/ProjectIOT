"""Real inference diagnostic. Exit 2 means structured output worked but known fixture facts differed."""
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.ocr import extract_text
from services.llm import analyze

start=time.monotonic()
text=extract_text(ROOT/'tests/fixtures/synthetic_receipt.png')
ocr_seconds=time.monotonic()-start
start=time.monotonic()
result=analyze(text,os.environ.get('LLAMA_URL','http://127.0.0.1:8081'))
ai_seconds=time.monotonic()-start
items=result['items']
checks={
    'merchant':result.get('merchant')=='ร้านทดสอบ',
    'date':result.get('date')=='2026-10-19',
    'receipt_total':result.get('receipt_total')=='45.50',
    'item_names':{item.get('name') for item in items}=={'ขนมปัง','นม'},
    'line_amounts':{item.get('name'):item.get('line_total') for item in items}=={'ขนมปัง':'15.50','นม':'30.00'},
    'categories':len(items)==2 and all(item.get('category')=='อาหารและเครื่องดื่ม' for item in items)
}
record={'fixture':'synthetic_receipt.png (not a real receipt)','platform':os.uname().machine,'pipeline_completed':True,
        'ocr_seconds':ocr_seconds,'ai_seconds':ai_seconds,'semantic_checks':checks,'result':result,
        'note':'Single synthetic fixture only. Human correction remains required. Not an accuracy benchmark.'}
output=Path(os.environ.get('MODEL_SMOKE_OUTPUT',str(ROOT/'test-results/model-smoke.json')))
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record,ensure_ascii=False,indent=2))
sys.exit(0 if all(checks.values()) else 2)
