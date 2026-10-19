#!/usr/bin/env bash
set -euo pipefail
cd /workspace/ProjectIOT
mkdir -p /workspace/receipt-tools /workspace/receipt-runtime/tessdata
python3 -m venv /workspace/receipt-tools/venv
export PATH="/workspace/receipt-tools/venv/bin:$PATH"
export PIP_CACHE_DIR=/workspace/receipt-tools/pip-cache
python -m pip install -r requirements-dev.txt cmake==4.4.4 ninja==1.13.2
command -v tesseract >/dev/null
tessdata_revision=87416418657359cb625c412a48b6e1d6d41c29bd
thai_file=/workspace/receipt-runtime/tessdata/tha.traineddata
thai_checksum=294227cc2d1292b0acb28d61d4115c88252b96d466ca90b417cf4cf0c67bf07c
if [[ ! -f "$thai_file" ]]; then
  curl --fail --location --retry 2 "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$tessdata_revision/tha.traineddata" -o "$thai_file.part"
  printf '%s  %s\n' "$thai_checksum" "$thai_file.part" | sha256sum --check -
  mv "$thai_file.part" "$thai_file"
fi
printf '%s  %s\n' "$thai_checksum" "$thai_file" | sha256sum --check -
if [[ ! -f /workspace/receipt-runtime/tessdata/eng.traineddata ]]; then
  cp /usr/share/tesseract-ocr/5/tessdata/eng.traineddata /workspace/receipt-runtime/tessdata/eng.traineddata
fi
llama_dir=/workspace/receipt-tools/llama.cpp
llama_revision=31288c9c66e59377f7788d920678a565bb89dd37
if [[ ! -e "$llama_dir" ]]; then
  git init "$llama_dir"
  git -C "$llama_dir" remote add origin https://github.com/ggml-org/llama.cpp.git
  git -C "$llama_dir" fetch --depth 1 origin "$llama_revision"
  git -C "$llama_dir" checkout --detach FETCH_HEAD
fi
if [[ "$(git -C "$llama_dir" rev-parse HEAD)" != "$llama_revision" ]] || [[ -n "$(git -C "$llama_dir" status --porcelain --untracked-files=no)" ]]; then
  printf '%s\n' 'Inspect existing llama.cpp revision or local changes; setup will not overwrite it.' >&2
  exit 1
fi
cmake -S "$llama_dir" -B "$llama_dir/build" -DGGML_NATIVE=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_UI=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build "$llama_dir/build" --target llama-server -j 2
export TESSDATA_PREFIX=/workspace/receipt-runtime/tessdata
python -m pytest -q
python scripts/download_model.py
