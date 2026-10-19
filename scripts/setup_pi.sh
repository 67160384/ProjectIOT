#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
if [[ "$(uname -m)" != aarch64 ]]; then
  printf '%s\n' 'This installer targets Raspberry Pi OS 64-bit (aarch64). See README for x86 development.' >&2
  exit 1
fi
if [[ "$EUID" == 0 ]]; then
  printf '%s\n' 'Run as your normal Pi user. The script uses sudo for system packages only.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip tesseract-ocr tesseract-ocr-tha tesseract-ocr-eng git cmake build-essential libssl-dev fonts-dejavu-core
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
llama_revision=31288c9c66e59377f7788d920678a565bb89dd37
mkdir -p tools models instance
if [[ ! -e tools/llama.cpp ]]; then
  git init tools/llama.cpp
  git -C tools/llama.cpp remote add origin https://github.com/ggml-org/llama.cpp.git
  git -C tools/llama.cpp fetch --depth 1 origin "$llama_revision"
  git -C tools/llama.cpp checkout --detach FETCH_HEAD
fi
if [[ "$(git -C tools/llama.cpp rev-parse HEAD)" != "$llama_revision" ]] || [[ -n "$(git -C tools/llama.cpp status --porcelain --untracked-files=no)" ]]; then
  printf '%s\n' 'Existing llama.cpp differs from the tested revision. Preserve local changes and inspect it before rebuilding.' >&2
  exit 1
fi
cmake -S tools/llama.cpp -B tools/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_UI=OFF -DGGML_NATIVE=ON
cmake --build tools/llama.cpp/build --target llama-server -j 2
.venv/bin/python scripts/download_model.py
tesseract --list-langs
printf '%s\n' 'Installation complete. Start with: bash scripts/start_llm.sh and bash scripts/start_web.sh (separate terminals).'
