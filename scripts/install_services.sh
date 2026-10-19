#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
service_user="$(id -un)"
if [[ "$EUID" == 0 || "$project_root" =~ [[:space:]%] ]]; then
  printf '%s\n' 'Run as your normal Pi user, from a project path without spaces or percent signs.' >&2
  exit 1
fi
[[ -x "$project_root/.venv/bin/python" && -x "$project_root/tools/llama.cpp/build/bin/llama-server" && -f "$project_root/models/model-manifest.json" ]] || { printf '%s\n' 'Run setup_pi.sh and manual smoke checks first.' >&2; exit 1; }
for service in receipt-llm receipt-web; do
  if [[ -e "/etc/systemd/system/$service.service" ]]; then
    printf '%s\n' "Existing $service.service found. Inspect it; this script will not overwrite it." >&2
    exit 1
  fi
done
service_tmp="$(mktemp -d)"
trap 'rm -rf "$service_tmp"' EXIT
for component in llm web; do
  script="start_${component}.sh"
  cat > "$service_tmp/receipt-$component.service" <<EOF
[Unit]
Description=Offline Receipt Analyzer $component
After=network.target

[Service]
Type=simple
User=$service_user
WorkingDirectory=$project_root
ExecStart=/bin/bash $project_root/scripts/$script
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
  sudo install -m 644 "$service_tmp/receipt-$component.service" "/etc/systemd/system/receipt-$component.service"
done
sudo systemctl daemon-reload
sudo systemctl enable --now receipt-llm receipt-web
printf '%s\n' 'Check: systemctl status receipt-llm receipt-web; then open the web page and check OCR/AI readiness.'
