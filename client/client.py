#!/usr/bin/env python3
"""nami-tui — minimal urwid client"""

import json, os, queue, socket, subprocess, sys, threading
from io import BytesIO
from pathlib import Path

import mutagen
import urwid
from PIL import Image

PORT = (json.loads((Path.home() / ".config" / "nami" / "config.json").read_text())
        if (Path.home() / ".config" / "nami" / "config.json").exists()
        else {}).get("port", 20224)

COLOR_CONFIG = Path.home() / ".config" / "nami" / "tui_colors.json"

PALETTE_DEFAULTS = {
    "head": ("white", "dark blue"),
    "foot": ("white", "dark blue"),
    "active": ("black", "yellow"),
    "playing": ("yellow,bold", ""),
    "selected": ("white", "dark cyan"),
}

COLOR_NAMES = [
    "default", "black", "dark red", "dark green", "brown",
    "dark blue", "dark magenta", "dark cyan", "light gray",
    "dark gray", "light red", "light green", "yellow",
    "light blue", "light magenta", "light cyan", "white",
]


class Conn:
    def __init__(self):
        self.sock = socket.create_connection(("127.0.0.1", PORT))
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._recv, daemon=True).start()

    def send(self, req):
        self.sock.sendall(json.dumps(req).encode() + b"\n")
        return self.q.get()

    def _recv(self):
        buf = b""
        while True:
            if not (chunk := self.sock.recv(4096)):
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self.q.put(json.loads(line))

    def close(self):
        self.sock.close()


class ClickListBox(urwid.ListBox):
    """ListBox that never auto-scrolls — only the highlight moves."""

    def make_cursor_visible(self, size):
        pass

    def mouse_event(self, size, event, button, col, row, focus):
        if button == 1 and event == "mouse press":
            super().mouse_event(size, event, button, col, row, focus)
            if hasattr(self, "_on_click"):
                self._on_click()
            return True
        return super().mouse_event(size, event, button, col, row, focus)


class App:
    def __init__(self):
        self.conn = Conn()
        self.state = self.conn.send({"request": "state", "params": {}})
        self.info = self.conn.send({"request": "info", "params": {}})
        self.lib: list[dict] = []
        self._tab = 0  # 0 = library, 1 = playlist
        self._art_path: str | None = None
        # vim key buffer
        self._keybuf: list[str] = []
        # color config
        self._color_mode = False
        self._color_focus = 0
        self._color_part = 0  # 0=fg, 1=bg
        self._colors = self._load_colors()
        self._build_ui()
        self._load_lib()

    def _hdr(self):
        s = self.state
        name = Path((s.get("current_music") or "")).stem or "no track"
        icons = {"playing": "▶", "paused": "⏸", "stopped": "⏹"}
        return f' {icons.get(s.get("status","stopped"),"⏹")} {name}  Vol: {s.get("volume",0)}%  [{s.get("status","?")}]'

    def _build_ui(self):
        # header
        self.hdr = urwid.Text(self._hdr(), align="left")
        # left pane
        self.tab_text = urwid.Text("", align="left")
        self.walker: urwid.SimpleFocusListWalker = urwid.SimpleFocusListWalker([])
        self.listbox = ClickListBox(self.walker)
        self.listbox._on_click = self._play_focused
        left_pile = urwid.Pile([("flow", self.tab_text), self.listbox])
        self.left_box = urwid.LineBox(left_pile, title=" Library ")
        # right pane (art + info)
        self.art_w = urwid.Text("", align="center")
        self.info_w = urwid.Text("", align="left")
        self.right_pile = urwid.Pile([
            ("flow", self.art_w),
            ("weight", 1, urwid.Filler(self.info_w, valign="top")),
        ])
        self.right_box = urwid.LineBox(self.right_pile, title=" Now Playing ")
        # color config pane (built on demand)
        self._color_box = None
        # body: two panes
        body = urwid.Columns([("weight", 2, self.left_box), ("weight", 1, self.right_box)])
        # footer
        help = "j/k nav  1 Library  2 Playlist  enter play  space toggle  c colors  q quit"
        self.foot = urwid.Text(help, align="left")
        # frame
        self.frame = urwid.Frame(
            body,
            header=urwid.AttrMap(self.hdr, "head"),
            footer=urwid.AttrMap(self.foot, "foot"),
        )
        self._refresh_tabs()
        self._refresh_right()

    # ── color config ──

    def _load_colors(self):
        try:
            return json.loads(COLOR_CONFIG.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_colors(self, colors):
        COLOR_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        COLOR_CONFIG.write_text(json.dumps(colors, indent=2))

    def _palette_from_colors(self, colors):
        pal = []
        for key, (df, db) in PALETTE_DEFAULTS.items():
            c = colors.get(key, {})
            pal.append((key, c.get("fg", df), c.get("bg", db)))
        return pal

    def _apply_palette(self):
        pal = self._palette_from_colors(self._colors)
        self._loop.screen.register_palette(pal)
        self._loop.draw_screen()

    # ── color picker ──

    def _toggle_color_mode(self):
        self._color_mode = not self._color_mode
        if self._color_mode:
            self._color_focus = 0
            self._color_part = 0
            self._rebuild_color_ui()
            body = self.frame.body
            body.contents[1] = (self._color_box, body.contents[1][1])
        else:
            self._save_colors(self._colors)
            body = self.frame.body
            body.contents[1] = (self.right_box, body.contents[1][1])

    def _rebuild_color_ui(self):
        rows = []
        for i, key in enumerate(PALETTE_DEFAULTS):
            c = self._colors.get(key, {})
            df, db = PALETTE_DEFAULTS[key]
            fg = c.get("fg", df)
            bg = c.get("bg", db)
            marker = ">" if i == self._color_focus else " "
            part = ""
            if i == self._color_focus:
                part = " [fg]" if self._color_part == 0 else " [bg]"
            rows.append(("flow", urwid.Text(f" {marker} {key:10} {fg:12} on {bg}")))
            check = " ◀" if i == self._color_focus else ""
            rows[-1] = ("flow", urwid.Text(f" {marker} {key:10} {fg:12} on {bg}{part}{check}"))
        rows.append(("flow", urwid.Text("")))
        rows.append(("flow", urwid.Text(" ↑↓ jk select  ←→ hl cycle  Tab fg/bg  C save")))
        self._color_pile = urwid.Pile(rows)
        self._color_box = urwid.LineBox(self._color_pile, title=" Color Config ")

    def _cycle_color(self, direction):
        key = list(PALETTE_DEFAULTS.keys())[self._color_focus]
        c = self._colors.get(key, {})
        df, db = PALETTE_DEFAULTS[key]
        current = c.get("fg", df) if self._color_part == 0 else c.get("bg", db)
        try:
            idx = COLOR_NAMES.index(current)
        except ValueError:
            idx = 0
        new = COLOR_NAMES[(idx + direction) % len(COLOR_NAMES)]
        if key not in self._colors:
            self._colors[key] = {}
        if self._color_part == 0:
            self._colors[key]["fg"] = new
        else:
            self._colors[key]["bg"] = new
        self._apply_palette()
        self._rebuild_color_ui()

    # ── album art ──

    def _extract_art(self) -> bytes | None:
        path = self.state.get("current_music", "")
        if not path:
            return None
        try:
            f = mutagen.File(path)
            if f and f.tags:
                for tag in f.tags.values():
                    if tag.FrameID == "APIC":
                        return tag.data
        except Exception:
            pass
        parent = Path(path).parent
        for name in ("cover.jpg", "cover.png", "front.jpg", "album.jpg", "folder.jpg"):
            p = parent / name
            if p.exists():
                return p.read_bytes()
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", path, "-f", "singlejpeg", "pipe:1"],
                capture_output=True, timeout=8)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except Exception:
            pass
        if path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp")):
            return Path(path).read_bytes()
        return None

    def _art_to_markup(self, data: bytes, cols: int, rows: int):
        img = Image.open(BytesIO(data)).convert("RGB")
        target_w = cols
        target_h = rows * 2
        img.thumbnail((target_w, target_h), Image.LANCZOS)
        w, h = img.size
        pixels = list(img.getdata())
        markup = []
        blank = urwid.AttrSpec("", "")
        for y in range(0, h, 2):
            for x in range(w):
                top = pixels[y * w + x]
                bot = pixels[(y + 1) * w + x] if y + 1 < h else (0, 0, 0)
                attr = urwid.AttrSpec(
                    f"#{bot[0]:02x}{bot[1]:02x}{bot[2]:02x}",
                    f"#{top[0]:02x}{top[1]:02x}{top[2]:02x}",
                )
                markup.append((attr, "▄"))
            if y + 2 < h:
                markup.append((blank, "\n"))
        return markup

    # ── data ──

    def _refresh_state(self):
        try:
            self.state = self.conn.send({"request": "state", "params": {}})
            self.info = self.conn.send({"request": "info", "params": {}})
            self.hdr.set_text(self._hdr())
            self._refresh_right()
        except Exception:
            pass

    def _refresh_right(self):
        path = self.state.get("current_music", "")
        if path != self._art_path:
            self._art_path = path
            raw = self._extract_art()
            if raw:
                m = self._art_to_markup(raw, 22, 10)
                self.art_w.set_text(m)
            else:
                self.art_w.set_text("  (no art)")
        lines = []
        if self.info and "error" not in self.info:
            for k in ("title", "artist", "album", "genre", "length"):
                lines.append(f"  {k}: {self.info.get(k, '—')}")
        self.info_w.set_text("\n".join(lines))

    def _load_lib(self):
        try:
            data = self.conn.send({"request": "database_list", "params": {}})
            self.lib = data.get("music", [])
        except Exception:
            self.lib = []
        self._show_list()

    def _load_playlist(self):
        try:
            self._show_list(self.conn.send(
                {"request": "get_playlist", "params": {}}
            ))
        except Exception:
            self._show_list()

    def _show_list(self, pl: dict | None = None):
        if self._tab == 0:
            items = [(m.get("title") or Path(m.get("path", "")).stem, False) for m in self.lib]
        else:
            raw = (pl or {}).get("playlist", [])
            cur = (pl or {}).get("current_index", -1)
            items = [(Path(i["path"]).stem, i["index"] == cur) for i in raw]
        if len(items) == len(self.walker):
            for i, (text, is_cur) in enumerate(items):
                w = self.walker[i]
                w.original_widget.set_text(f" {text}")
                if self._tab == 1:
                    w.attr_map = {None: "playing"} if is_cur else {None: None}
            return
        focus_idx = self.walker.get_focus()[1] or 0
        self.walker.clear()
        for text, is_cur in items:
            inner = urwid.Text(f" {text}")
            if is_cur and self._tab == 1:
                self.walker.append(urwid.AttrMap(inner, "playing", "selected"))
            else:
                self.walker.append(urwid.AttrMap(inner, None, "selected"))
        if self.walker:
            self.walker.set_focus(min(focus_idx, len(self.walker) - 1))

    def _refresh_tabs(self):
        self.tab_text.set_text(
            "  [1] Library   [2] Playlist" if self._tab == 0
            else "   Library   [2] Playlist")
        self.left_box.title = " Library " if self._tab == 0 else " Playlist "

    def _switch_tab(self, n: int):
        if n == self._tab:
            return
        self._tab = n
        self._refresh_tabs()
        if n == 0:
            self._show_list()
        else:
            self._load_playlist()

    # ── actions ──

    def _play_focused(self):
        if not self.walker:
            return
        focus = self.walker.get_focus()
        if focus[1] is None:
            return
        idx = focus[1]
        if self._tab == 0:
            if 0 <= idx < len(self.lib):
                self.conn.send({"request": "load", "params": {"path": self.lib[idx]["path"]}})
                self.conn.send({"request": "play", "params": {}})
                self._refresh_state()
        else:
            self.conn.send({"request": "play_index", "params": {"index": idx}})
            self._refresh_state()

    def _cmd(self, req: str, **kw):
        try:
            self.conn.send({"request": req, "params": kw})
            self._refresh_state()
            if self._tab == 1:
                self._load_playlist()
        except Exception:
            pass

    def _walk(self, direction: int):
        """Move walker focus by direction (-1 up, +1 down)."""
        pos = self.walker.focus
        if pos is None:
            return
        new = pos + direction
        if 0 <= new < len(self.walker):
            self.walker.set_focus(new)

    # ── keys ──

    def _color_keypress(self, key):
        n = len(PALETTE_DEFAULTS)
        if key in ("j", "down"):
            self._color_focus = min(n - 1, self._color_focus + 1)
            self._rebuild_color_ui()
            return True
        if key in ("k", "up"):
            self._color_focus = max(0, self._color_focus - 1)
            self._rebuild_color_ui()
            return True
        if key in ("h", "left"):
            self._cycle_color(-1)
            return True
        if key in ("l", "right"):
            self._cycle_color(1)
            return True
        if key == "tab":
            self._color_part = 1 - self._color_part
            self._rebuild_color_ui()
            return True
        if key in ("c", "C"):
            self._toggle_color_mode()
            return True
        if key == "q":
            self._toggle_color_mode()
            return True
        return None

    def keypress(self, key):
        # color mode keys
        if self._color_mode:
            return self._color_keypress(key) or True

        # ── multi-key sequences ──
        if key == "g":
            self._keybuf.append("g")
            if len(self._keybuf) >= 2:
                self._keybuf.clear()
                if self.walker:
                    self.walker.set_focus(0)
            return True
        self._keybuf.clear()

        if key == "G":
            self._keybuf.clear()
            if self.walker:
                self.walker.set_focus(len(self.walker) - 1)
            return True

        # ── navigation ──
        if key == "j":
            self._walk(1)
            return True
        if key == "k":
            self._walk(-1)
            return True

        # ── actions ──
        if key == "q":
            raise urwid.ExitMainLoop()
        if key == "1":
            self._switch_tab(0)
        elif key == "2":
            self._switch_tab(1)
        elif key == "enter":
            self._play_focused()
        elif key == " ":
            self._cmd("toggle")
        elif key == "s":
            self._cmd("stop")
        elif key == "n":
            self._cmd("next")
        elif key == "p":
            self._cmd("previous")
        elif key in ("c", "C"):
            if not self._color_mode:
                self._toggle_color_mode()
        elif key in ("+", "="):
            v = min(150, self.state.get("volume", 0) + 5)
            self._cmd("volume", volume=v)
        elif key in ("-", "_"):
            v = max(0, self.state.get("volume", 0) - 5)
            self._cmd("volume", volume=v)
        else:
            return None
        return True

    def run(self):
        pal = self._palette_from_colors(self._colors)
        loop = urwid.MainLoop(
            self.frame, pal, unhandled_input=self.keypress,
        )
        self._loop = loop
        loop.run()


if __name__ == "__main__":
    if not sys.stdin.isatty():
        print("need a terminal"); sys.exit(1)
    try:
        App().run()
    except (urwid.ExitMainLoop, KeyboardInterrupt):
        pass
