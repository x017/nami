#!/usr/bin/env python3
"""nami-cli — terminal client for Nami music server"""

import json, os, queue, socket, subprocess, sys, threading
from io import BytesIO
from pathlib import Path

import mutagen
import urwid
from PIL import Image
from tqdm import tqdm

PORT = (json.loads((Path.home() / ".config" / "nami" / "config.json").read_text())
        if (Path.home() / ".config" / "nami" / "config.json").exists()
        else {}).get("port", 20224)

COLOR_CONFIG = Path.home() / ".config" / "nami" / "tui_colors.json"

PALETTE_DEFAULTS = {
    "head": ("white", "dark blue"),
    "keybind": ("white", "dark blue"),
    "active": ("black", "yellow"),
    "playing": ("yellow,bold", ""),
    "selected": ("white", "dark cyan"),
    "label": ("dark cyan", ""),
    "tab_active": ("yellow,bold", ""),
    "tab_inactive": ("dark gray", ""),
    "progress": ("light green", ""),
    "border": ("dark gray", ""),
    "list_item": ("default", "default"),
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
        self.pos: dict = {}
        self.lib: list[dict] = []
        self._tab = 0  # 0 = library, 1 = playlist
        self._art_path: str | None = None
        # vim key buffer
        self._keybuf: list[str] = []
        # color config
        self._color_mode = False
        self._color_focus = 0
        self._color_part = 0  # 0=fg, 1=bg
        self._hex_mode = False
        self._hex_buf = ""
        self._colors = self._load_colors()
        self._search_mode = False
        self._search_buf = ""
        self._save_mode = False
        self._save_buf = ""
        self._saved: list[Path] = []
        self._build_ui()
        self._load_lib()

    @staticmethod
    def _fmt_time(ms: int) -> str:
        if ms <= 0:
            return "--:--"
        sec = ms // 1000
        return f"{sec // 60}:{sec % 60:02d}"

    def _tqdm_text(self) -> str:
        p = self.pos
        dur = p.get("duration_ms", 0) or 0
        cur = p.get("position_ms", 0) or 0
        if dur <= 0:
            return ""
        return tqdm.format_meter(
            cur // 1000, dur // 1000, cur / 1000,
            ncols=48, ascii=False, unit="",
            bar_format="{percentage:3.0f}% {bar}",
        )

    def _duration_text(self) -> str:
        p = self.pos
        dur = p.get("duration_ms", 0) or 0
        cur = p.get("position_ms", 0) or 0
        if dur <= 0:
            return ""
        return f"{self._fmt_time(cur)} / {self._fmt_time(dur)}"

    def _hdr(self):
        s = self.state
        name = Path((s.get("current_music") or "")).stem or "no track"
        icons = {"playing": "▶", "paused": "⏸", "stopped": "⏹"}
        icon = icons.get(s.get("status", "stopped"), "⏹")
        return f" {icon} {name}  Vol: {s.get('volume', 0)}%"

    def _build_ui(self):
        # header
        self.hdr = urwid.Text(self._hdr(), align="left")
        # left pane
        self.tab_text = urwid.Text("", align="left")
        self.search_text = urwid.Text("", align="left")
        self.save_text = urwid.Text("", align="left")
        self.walker: urwid.SimpleFocusListWalker = urwid.SimpleFocusListWalker([])
        self.listbox = ClickListBox(self.walker)
        self.listbox._on_click = self._play_focused
        left_pile = urwid.Pile([("flow", self.tab_text), ("flow", self.search_text), ("flow", self.save_text), self.listbox])
        self.left_box = urwid.LineBox(left_pile, title=" Library ")
        # right pane (art + info + duration)
        self.art_w = urwid.Text("", align="center")
        self.info_w = urwid.Text("", align="left")
        dur_t = urwid.Text("", align="center")
        prog_t = urwid.Text("", align="center")
        self.duration_w = urwid.AttrMap(dur_t, "progress")
        self.progress_w = urwid.AttrMap(prog_t, "progress")
        self.right_pile = urwid.Pile([
            ("flow", self.art_w),
            ("weight", 1, urwid.Filler(self.info_w, valign="top")),
            ("flow", self.duration_w),
            ("flow", self.progress_w),
        ])
        self.right_box = urwid.LineBox(self.right_pile, title=" Now Playing ")
        # color config pane
        self._color_pile = urwid.Pile([])
        self._color_box = urwid.LineBox(self._color_pile, title=" Color Config ")
        # body: two panes
        body = urwid.Columns([
            ("weight", 2, urwid.AttrMap(self.left_box, "border")),
            ("weight", 1, urwid.AttrMap(self.right_box, "border")),
        ])
        # footer
        help = "j/k nav  1-3 tabs  enter play  space toggle  hl seek  a add  d rm  S save  enter/load  c colors  q quit"
        self.foot = urwid.Text(help, align="left")
        # frame
        self.frame = urwid.Frame(
            body,
            header=urwid.AttrMap(self.hdr, "head"),
            footer=urwid.AttrMap(self.foot, "keybind"),
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
            fg = c.get("fg", df)
            bg = c.get("bg", db)
            basic_fg = fg if fg in COLOR_NAMES else df
            basic_bg = bg if bg in COLOR_NAMES else db
            pal.append((key, basic_fg, basic_bg, None, fg, bg))
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
            body.contents[1] = (urwid.AttrMap(self.right_box, "border"), body.contents[1][1])

    def _rebuild_color_ui(self):
        rows = []
        rows.append((urwid.Text(" j/k entry  h/l color  Tab fg⇔bg  x type  Enter/esc confirm", align="center"), ("pack", None)))
        rows.append((urwid.Text(""), ("pack", None)))
        for i, key in enumerate(PALETTE_DEFAULTS):
            c = self._colors.get(key, {})
            df, db = PALETTE_DEFAULTS[key]
            fg = c.get("fg", df)
            bg = c.get("bg", db)
            marker = ">" if i == self._color_focus else " "
            part = f" [{'fg' if self._color_part == 0 else 'bg'}]" if i == self._color_focus else ""
            check = " ◀" if i == self._color_focus else ""
            if self._hex_mode and i == self._color_focus:
                display = self._hex_buf if self._hex_buf else "_"
                rows.append((urwid.Text(f" {marker} {key:10} {display:12} on {bg if self._color_part else fg}{part}{check}"), ("pack", None)))
            else:
                rows.append((urwid.Text(f" {marker} {key:10} {fg:12} on {bg}{part}{check}"), ("pack", None)))
        rows.append((urwid.Text(""), ("pack", None)))
        rows.append((urwid.Text(" j/k entry  h/l color  Tab fg⇔bg  x type hex  c save  q discard", align="center"), ("pack", None)))
        self._color_pile.contents = rows

    def _cycle_color(self, direction):
        key = list(PALETTE_DEFAULTS.keys())[self._color_focus]
        c = self._colors.get(key, {})
        df, db = PALETTE_DEFAULTS[key]
        current = c.get("fg", df) if self._color_part == 0 else c.get("bg", db)
        if current in COLOR_NAMES:
            idx = COLOR_NAMES.index(current)
        else:
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

    def _refresh_position(self, loop=None, data=None):
        try:
            self.pos = self.conn.send({"request": "position", "params": {}})
            self.progress_w.original_widget.set_text(self._tqdm_text())
            self.duration_w.original_widget.set_text(self._duration_text())
        except Exception:
            pass
        if loop:
            loop.set_alarm_in(1, self._refresh_position)

    def _refresh_right(self):
        path = self.state.get("current_music", "")
        if path != self._art_path:
            self._art_path = path
            self.duration_w.original_widget.set_text("")
            self.progress_w.original_widget.set_text("")
            raw = self._extract_art()
            if raw:
                m = self._art_to_markup(raw, 22, 10)
                self.art_w.set_text(m)
            else:
                self.art_w.set_text("")
        markup = []
        if self.info and "error" not in self.info:
            for k in ("title", "artist", "album"):
                v = self.info.get(k, "—")
                markup += [("label", f" {k}\n"), ("value", f"  {v}\n")]
        self.info_w.set_text(markup)

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

    PLAYLIST_DIR = Path.home() / ".config" / "nami" / "playlists"

    def _save_playlist(self):
        try:
            data = self.conn.send({"request": "get_playlist", "params": {}})
            songs = [i["path"] for i in data.get("playlist", [])]
            self.PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
            n = len(list(self.PLAYLIST_DIR.iterdir())) + 1
            (self.PLAYLIST_DIR / f"playlist_{n}.json").write_text(json.dumps(songs, indent=2))
            self.foot.set_text(f" saved playlist_{n}")
        except Exception:
            pass

    def _load_playlist_file(self, index: int = -1):
        try:
            self.PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
            files = sorted(self.PLAYLIST_DIR.glob("*.json"))
            if not files:
                self.foot.set_text(" no saved playlists")
                return
            if index < 0:
                index = len(files) - 1
            songs = json.loads(files[index].read_text())
            for path in songs:
                self.conn.send({"request": "add_to_playlist", "params": {"path": path}})
            self.foot.set_text(f" loaded {files[index].stem} ({len(songs)} songs)")
            self._refresh_state()
            self._load_playlist()
        except Exception:
            pass

    def _update_save(self):
        if self._save_mode:
            self.save_text.set_text(f" Save as: {self._save_buf}▌")
        else:
            self.save_text.set_text("")

    def _save_playlist(self, name: str | None = None):
        try:
            data = self.conn.send({"request": "get_playlist", "params": {}})
            songs = [i["path"] for i in data.get("playlist", [])]
            self.PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
            if not name:
                n = len(list(self.PLAYLIST_DIR.iterdir())) + 1
                name = f"playlist_{n}"
            (self.PLAYLIST_DIR / f"{name}.json").write_text(json.dumps(songs, indent=2))
            self.foot.set_text(f" saved {name}")
        except Exception:
            pass

    def _load_saved(self):
        try:
            self.PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
            self._saved = sorted(self.PLAYLIST_DIR.glob("*.json"))
        except Exception:
            self._saved = []
        self._show_list()

    def _delete_saved(self, index: int):
        if 0 <= index < len(self._saved):
            self._saved[index].unlink()
            self._load_saved()

    def _filter_lib(self):
        if not self._search_buf:
            return self.lib
        q = self._search_buf.lower()
        return [m for m in self.lib
                if q in (m.get("title") or "").lower()
                or q in Path(m.get("path", "")).stem.lower()]

    def _update_search(self):
        if self._search_mode:
            self.search_text.set_text(f" / {self._search_buf}▌")
            self.left_box.title = " Search "
        else:
            self.search_text.set_text("")
            self.left_box.title = " Library "
        self._show_list()

    def _show_list(self, pl: dict | None = None):
        if self._tab == 0:
            items = [(m.get("title") or Path(m.get("path", "")).stem, False) for m in self._filter_lib()]
        elif self._tab == 1:
            raw = (pl or {}).get("playlist", [])
            cur = (pl or {}).get("current_index", -1)
            items = [(Path(i["path"]).stem, i["index"] == cur) for i in raw]
        else:
            items = [(p.stem, False) for p in self._saved]
        if len(items) == len(self.walker):
            for i, (text, is_cur) in enumerate(items):
                w = self.walker[i]
                label = f"▶ {text}" if is_cur else f"  {text}" if self._tab == 1 else f" {text}"
                w.original_widget.set_text(label)
                if self._tab == 1:
                    w.attr_map = {None: "playing"} if is_cur else {None: "list_item"}
            return
        focus_idx = self.walker.get_focus()[1] or 0
        self.walker.clear()
        for text, is_cur in items:
            label = f"▶ {text}" if is_cur else f"  {text}" if self._tab == 1 else f" {text}"
            inner = urwid.Text(label)
            if is_cur and self._tab == 1:
                self.walker.append(urwid.AttrMap(inner, "playing", "selected"))
            else:
                self.walker.append(urwid.AttrMap(inner, "list_item", "selected"))
        if self.walker:
            self.walker.set_focus(min(focus_idx, len(self.walker) - 1))

    def _refresh_tabs(self):
        labs = [" [1] Library ", " [2] Playlist ", " [3] Saved "]
        mk = []
        for i, lab in enumerate(labs):
            attr = "tab_active" if i == self._tab else "tab_inactive"
            mk.append((attr, lab))
        self.tab_text.set_text(mk)
        titles = [" Library ", " Playlist ", " Saved "]
        self.left_box.title = titles[self._tab]

    def _switch_tab(self, n: int):
        if n == self._tab:
            return
        self._search_mode = False
        self._search_buf = ""
        self._update_search()
        self._save_mode = False
        self._update_save()
        self._tab = n
        self._refresh_tabs()
        if n == 0:
            self._show_list()
        elif n == 1:
            self._load_playlist()
        else:
            self._load_saved()

    # ── actions ──

    def _play_focused(self):
        if not self.walker:
            return
        focus = self.walker.get_focus()
        if focus[1] is None:
            return
        idx = focus[1]
        if self._tab == 0:
            flib = self._filter_lib()
            if 0 <= idx < len(flib):
                self.conn.send({"request": "load", "params": {"path": flib[idx]["path"]}})
                self.conn.send({"request": "play", "params": {}})
                self._refresh_state()
        elif self._tab == 1:
            self.conn.send({"request": "play_index", "params": {"index": idx}})
            self._refresh_state()
        elif self._tab == 2:
            self._load_playlist_file(idx)
            self._switch_tab(1)

    def _cmd(self, req: str, **kw):
        try:
            self.conn.send({"request": req, "params": kw})
            self._refresh_state()
            if self._tab == 1:
                self._load_playlist()
            elif self._tab == 2:
                self._load_saved()
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

    @staticmethod
    def _valid_color(s: str) -> bool:
        if s in COLOR_NAMES:
            return True
        if s.startswith("#") and len(s) in (4, 7) and all(c in "0123456789abcdefABCDEF" for c in s[1:]):
            return True
        return False

    def _color_keypress(self, key):
        n = len(PALETTE_DEFAULTS)

        if self._hex_mode:
            if key == "enter":
                if self._valid_color(self._hex_buf):
                    key_name = list(PALETTE_DEFAULTS.keys())[self._color_focus]
                    if key_name not in self._colors:
                        self._colors[key_name] = {}
                    if self._color_part == 0:
                        self._colors[key_name]["fg"] = self._hex_buf
                    else:
                        self._colors[key_name]["bg"] = self._hex_buf
                    self._apply_palette()
                self._hex_mode = False
                self._rebuild_color_ui()
                return True
            if key == "esc":
                self._hex_mode = False
                self._rebuild_color_ui()
                return True
            if key == "backspace":
                self._hex_buf = self._hex_buf[:-1]
                self._rebuild_color_ui()
                return True
            if key in "0123456789abcdefABCDEF#":
                if len(self._hex_buf) < 7:
                    self._hex_buf += key
                    self._rebuild_color_ui()
                return True
            return True

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
        if key in ("x", "X"):
            key_name = list(PALETTE_DEFAULTS.keys())[self._color_focus]
            c = self._colors.get(key_name, {})
            df, db = PALETTE_DEFAULTS[key_name]
            current = c.get("fg", df) if self._color_part == 0 else c.get("bg", db)
            self._hex_buf = current
            self._hex_mode = True
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

        # ── save mode ──
        if self._save_mode:
            if key == "esc":
                self._save_mode = False
                self._save_buf = ""
                self._update_save()
                return True
            if key == "enter":
                name = self._save_buf.strip()
                if name:
                    self._save_playlist(name)
                    self._save_mode = False
                    self._update_save()
                    self._load_saved()
                return True
            if key == "backspace":
                self._save_buf = self._save_buf[:-1]
                self._update_save()
                return True
            if len(key) == 1:
                self._save_buf += key
                self._update_save()
                return True
            return True

        # ── search mode ──
        if self._search_mode:
            if key == "esc":
                self._search_mode = False
                self._search_buf = ""
                self._update_search()
                return True
            if key == "enter":
                flib = self._filter_lib()
                focus = self.walker.get_focus()
                if focus[1] is not None and 0 <= focus[1] < len(flib):
                    path = flib[focus[1]]["path"]
                    self._search_mode = False
                    self._search_buf = ""
                    self._update_search()
                    self.conn.send({"request": "load", "params": {"path": path}})
                    self.conn.send({"request": "play", "params": {}})
                    self._refresh_state()
                    return True
            if key == "backspace":
                self._search_buf = self._search_buf[:-1]
                self._update_search()
                return True
            if len(key) == 1:
                self._search_buf += key
                self._update_search()
                return True
            return True

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
        elif key == "3":
            self._switch_tab(2)
        elif key == "/":
            if self._tab == 0:
                self._search_mode = True
                self._search_buf = ""
                self._update_search()
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
        elif key == "a":
            if self._tab == 0:
                focus = self.walker.get_focus()
                flib = self._filter_lib()
                if focus[1] is not None and 0 <= focus[1] < len(flib):
                    self._cmd("add_to_playlist", path=flib[focus[1]]["path"])
        elif key == "d":
            if self._tab == 1:
                focus = self.walker.get_focus()
                if focus[1] is not None:
                    self._cmd("remove_from_playlist", index=focus[1])
            elif self._tab == 2:
                focus = self.walker.get_focus()
                if focus[1] is not None:
                    self._delete_saved(focus[1])
        elif key == "D":
            if self._tab == 1:
                self._cmd("clear_playlist")
        elif key == "S":
            if self._tab == 1:
                self._save_mode = True
                self._save_buf = ""
                self._update_save()
        elif key == "o":
            if self._tab == 1:
                self._load_playlist_file()
        elif key in ("c", "C"):
            if not self._color_mode:
                self._toggle_color_mode()
        elif key in ("h", "left"):
            self._cmd("backward", seconds=5)
        elif key in ("l", "right"):
            self._cmd("forward", seconds=5)
        elif key == "H":
            self._cmd("backward", seconds=30)
        elif key == "L":
            self._cmd("forward", seconds=30)
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
        screen = urwid.raw_display.Screen()
        screen.colors = 2**24
        loop = urwid.MainLoop(
            self.frame, pal, screen=screen, unhandled_input=self.keypress,
        )
        self._loop = loop
        self._refresh_position(loop)
        loop.run()


def main():
    if not sys.stdin.isatty():
        print("need a terminal"); sys.exit(1)
    try:
        App().run()
    except (urwid.ExitMainLoop, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
