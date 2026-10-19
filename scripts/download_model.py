"""Fetch the official GGUF at an immutable revision and verify its published LFS SHA256."""
import hashlib
import json
import os
from pathlib import Path
import requests
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
REPO='Qwen/Qwen2.5-0.5B-Instruct-GGUF'
FILENAME='qwen2.5-0.5b-instruct-q4_k_m.gguf'


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def main():
    directory=ROOT/'models';directory.mkdir(exist_ok=True)
    target=directory/FILENAME
    manifest=directory/'model-manifest.json'
    if manifest.exists():
        metadata=json.loads(manifest.read_text())
        if metadata.get('repository')!=REPO or metadata.get('filename')!=FILENAME:
            raise RuntimeError('Existing manifest does not match the selected model; inspect it before changing anything.')
    else:
        response=requests.get(f'https://huggingface.co/api/models/{REPO}?blobs=true',timeout=30)
        response.raise_for_status();info=response.json()
        item=next(item for item in info['siblings'] if item['rfilename']==FILENAME)
        metadata={'repository':REPO,'revision':info['sha'],'filename':FILENAME,'sha256':item['lfs']['sha256'],'size':item['lfs']['size']}
    if target.exists():
        if digest(target)!=metadata['sha256']:
            raise RuntimeError('Existing model checksum mismatch. Move the file aside and retry; it was not overwritten.')
        print('Model already present; SHA256 verified.')
    else:
        part=target.with_suffix('.part')
        url=f"https://huggingface.co/{REPO}/resolve/{metadata['revision']}/{FILENAME}"
        try:
            with requests.get(url,stream=True,timeout=(30,120)) as response:
                response.raise_for_status()
                with part.open('wb') as file:
                    for block in response.iter_content(1024*1024):file.write(block)
            if part.stat().st_size!=metadata['size'] or digest(part)!=metadata['sha256']:
                raise RuntimeError('Downloaded model failed size or SHA256 verification.')
            part.replace(target)
        finally:
            part.unlink(missing_ok=True)
    manifest.write_text(json.dumps(metadata,indent=2)+'\n')
    print(f'Verified model: {target}')


if __name__=='__main__':
    try:
        main()
    except requests.RequestException as exc:
        host=urlsplit(exc.request.url).hostname if exc.request is not None else 'huggingface.co'
        print(f'Download failed at {host}: {type(exc).__name__}. Check network access and retry. TLS verification remains enabled.',file=sys.stderr)
        sys.exit(1)
