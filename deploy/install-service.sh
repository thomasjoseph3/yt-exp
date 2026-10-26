#!/usr/bin/env bash
# Installs the studio as a systemd user service so it runs 24/7 and restarts on failure.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
UV="$(command -v uv)"
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/thoma-studio.service <<UNIT
[Unit]
Description=Thoma Explains video studio
After=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=$UV run thoma daemon
Restart=always
RestartSec=60
Environment=PATH=$PATH

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now thoma-studio
loginctl enable-linger "$USER"   # keep running after you log out
echo "Running. Logs: journalctl --user -u thoma-studio -f   (or data/studio.log)"
