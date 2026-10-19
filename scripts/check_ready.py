import json
import os
import sys
import requests

url=os.environ.get('RECEIPT_URL','http://127.0.0.1:5000')
with requests.Session() as client:
    client.trust_env=False
    response=client.get(url+'/health',timeout=10)
    response.raise_for_status()
    result=response.json()
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(0 if result['full_pipeline_ready'] else 1)
