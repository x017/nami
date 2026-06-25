# Nami 波 — music player daemon + TUI client

Nami is an MPD-like music player with a terminal UI. It runs as a headless daemon (VLC-backed) and connects to a client `nami-cli` over TCP.

## Install

### One-liner

```bash
curl -fsSL https://raw.githubusercontent.com/x017/nami/main/install.sh | bash
```

Requires Python 3.12+, [VLC](https://www.videolan.org/vlc/), and `pkg-config`. Installs the daemon as a systemd user service and makes `nami-cli` available in `~/.local/bin`.

### Manual

### Dependencies

- Python 3.12+
- [VLC](https://www.videolan.org/vlc/) (`libvlc` + `libvlccore`)
- `pkg-config`, `python3-pip`
- GLib/GIO (`libgirepository1.0-dev` on Debian, `gobject-introspection-devel` on Fedora) — only needed for MPRIS support

### From source

```bash
git clone <repo> && cd nami
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Run the daemon

```bash
python main.py            # starts on port 20224
```

Or install as a systemd user service:

```bash
bash scripts/install-daemon.sh
systemctl --user start nami
```

### Run the client

```bash
python client/client.py
```

Or build a standalone binary and symlink:

```bash
pip install pyinstaller
pyinstaller --onefile client/client.py --name nami-cli
ln -s "$PWD/dist/nami-cli" ~/.local/bin/nami-cli
nami-cli
```

## Usage

```
j/k          navigate list
enter         play focused item
space         toggle play/pause
h/l          seek -5/+5 seconds
H/L          seek -30/+30 seconds
n/p          next/previous track
1/2          switch Library / Playlist tab
a            add focused song to playlist (Library tab)
d/D          remove / clear playlist (Playlist tab)
S/o          save / load playlist to disk
/            search library (Esc to cancel)
s            stop
+/-          volume
c            open color config
q            quit
```

## Protocol

The daemon listens on TCP port `20224` (configurable in `~/.config/nami/config.json`). Communication is JSON-line: each request is a JSON object followed by `\n`; each response is a JSON object followed by `\n`.

### Request format

```json
{"request": "<command>", "params": {...}}
```

### Commands

| Command | Params | Response |
|---|---|---|
| `state` | `{}` | `{"status": "playing"|"paused"|"stopped", "current_music": "...", "volume": 0-150}` |
| `position` | `{}` | `{"position_ms": int, "duration_ms": int, "position_pct": float}` |
| `info` | `{}` | `{"title": "...", "artist": "...", "album": "...", "path": "..."}` |
| `load` | `{"path": "/path/to/file"}` | `{"current_music": "..."}` |
| `play` | `{}` | `{"status": "playing"}` |
| `toggle` | `{}` | `{"status": "playing"|"paused"}` |
| `stop` | `{}` | `{"status": "stopped"}` |
| `next` | `{}` | `{"status": "playing"}` |
| `previous` | `{}` | `{"status": "playing"}` |
| `forward` | `{"seconds": int}` | `{"position_ms": int}` |
| `backward` | `{"seconds": int}` | `{"position_ms": int}` |
| `volume` | `{"volume": 0-150}` | `{"volume": int}` |
| `database_list` | `{}` | `{"music": [{"title": "...", "path": "...", ...}]}` |
| `database_search` | `{"query": "..."}` | `{"music": [...]}` |
| `database_refresh` | `{}` | `{"count": int}` |
| `get_playlist` | `{}` | `{"playlist": [{"index": int, "path": "..."}], "current_index": int}` |
| `add_to_playlist` | `{"path": "..."}` | `{"playlist_length": int}` |
| `remove_from_playlist` | `{"index": int}` | `{"playlist_length": int}` |
| `clear_playlist` | `{}` | `{"playlist_length": 0}` |
| `play_index` | `{"index": int}` | `{"current_index": int}` |

## MPRIS

The daemon exposes a [MPRIS 2.1](https://specifications.freedesktop.org/mpris-spec/latest/) D-Bus interface for desktop integration (media keys, lock screen controls, etc.):

| Item | Value |
|---|---|
| Bus name | `org.mpris.MediaPlayer2.nami` |
| Object path | `/org/mpris/MediaPlayer2` |
| Interfaces | `org.mpris.MediaPlayer2`, `org.mpris.MediaPlayer2.Player` |

Requires `dasbus` and `PyGObject` (installed by default via `requirements.txt`). The service starts automatically with the daemon; no extra config needed.

### Example

```json
--> {"request": "state", "params": {}}
<-- {"status": "playing", "current_music": "/music/song.flac", "volume": 100}
```

## Color config

Press `c` to open the color picker. Custom colors are saved to `~/.config/nami/tui_colors.json`. Supported values: ANSI color names (`dark blue`, `yellow`, etc.) and hex codes (`#c0caf5`).

Palette entries: `head`, `keybind`, `active`, `playing`, `selected`, `label`, `tab_active`, `tab_inactive`, `progress`, `border`, `list_item`.
