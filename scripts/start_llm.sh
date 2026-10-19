#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
llama_bin="${LLAMA_BIN:-$project_root/tools/llama.cpp/build/bin/llama-server}"
model_file="${MODEL_PATH:-$project_root/models/qwen2.5-0.5b-instruct-q4_k_m.gguf}"
[[ -x "$llama_bin" ]] || { printf '%s\n' 'llama-server is missing. Run setup first.' >&2; exit 1; }
[[ -f "$model_file" ]] || { printf '%s\n' 'GGUF model is missing. Run scripts/download_model.py first.' >&2; exit 1; }
exec "$llama_bin" -m "$model_file" --alias receipt-qwen --host 127.0.0.1 --port 8081 -c 2048 -t 4 -np 1 -ngl 0 --offline --no-webui
