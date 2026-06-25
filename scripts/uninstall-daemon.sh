#!/usr/bin/env bash
set -euo pipefail

echo "==> Stopping nami service"
systemctl --user stop nami 2>/dev/null || true

echo "==> Disabling nami (removes from startup)"
systemctl --user disable nami 2>/dev/null || true

echo "==> Removing service file"
rm -f "$HOME/.config/systemd/user/nami.service"

echo "==> Reloading systemd user daemon"
systemctl --user daemon-reload

echo "==> Removing binary"
rm -f "$HOME/.local/bin/nami"

echo "Done."
