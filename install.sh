#!/usr/bin/env bash
# Nami one-liner installer
#   curl -fsSL https://raw.githubusercontent.com/x017/nami/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/x017/nami.git"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/nami"
BIN="$HOME/.local/bin"

echo "==> Cloning nami into $DEST"
if [ -d "$DEST" ]; then
  echo "    already exists, pulling updates..."
  git -C "$DEST" pull --ff-only
else
  git clone "$REPO" "$DEST"
fi

echo "==> Setting up Python virtual environment"
python3 -m venv "$DEST/.venv"
source "$DEST/.venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$DEST/requirements.txt"

echo "==> Making nami-cli available"
mkdir -p "$BIN"
cat > "$BIN/nami-cli" <<'SCRIPT'
#!/usr/bin/env bash
exec "$HOME/.local/share/nami/.venv/bin/python3" "$HOME/.local/share/nami/client/client.py" "$@"
SCRIPT
chmod +x "$BIN/nami-cli"

echo "==> Building daemon binary with PyInstaller"
pip install -q pyinstaller
cd "$DEST"
python build.py 2>&1 | tail -5

echo "==> Installing daemon"
mkdir -p "$BIN"
cp "$DEST/dist/nami" "$BIN/nami"
mkdir -p "$HOME/.config/systemd/user"
cp "$DEST/nami.service" "$HOME/.config/systemd/user/nami.service"
systemctl --user daemon-reload
systemctl --user enable nami
systemctl --user start nami

echo ""
echo "==========  Done  =========="
echo ""
echo "  Start client:   nami-cli"
echo "  Daemon status:  systemctl --user status nami"
echo "  Daemon logs:    journalctl --user -u nami -f"
echo ""
echo "  Make sure ~/.local/bin is in your PATH."
echo "  Music path defaults to ~/Music — edit ~/.config/nami/config.json"
echo ""
