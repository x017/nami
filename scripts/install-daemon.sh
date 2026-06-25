#!/usr/bin/env bash
set -euo pipefail

ROOT="$(dirname "$(realpath "$0")")/.."
BINARY="$ROOT/dist/nami"
SERVICE="$ROOT/nami.service"

echo "==> Installing nami binary to ~/.local/bin/nami"
mkdir -p "$HOME/.local/bin"
cp "$BINARY" "$HOME/.local/bin/nami"
chmod +x "$HOME/.local/bin/nami"

echo "==> Installing systemd user service"
mkdir -p "$HOME/.config/systemd/user"
cp "$SERVICE" "$HOME/.config/systemd/user/nami.service"

echo "==> Reloading systemd user daemon"
systemctl --user daemon-reload

echo "==> Enabling nami (starts on boot)"
systemctl --user enable nami

echo "==> Starting nami now"
systemctl --user start nami

echo ""
echo "Status:"
systemctl --user status nami --no-pager
