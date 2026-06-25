"""MPRIS 2.1 D-Bus interface for Nami."""

import os
import threading
from pathlib import Path
from urllib.parse import quote

from gi.repository import GLib
from dasbus.connection import SessionMessageBus
from dasbus.loop import EventLoop
from dasbus.signal import Signal
from dasbus.typing import Str, Bool, Double, Int64, ObjPath, Variant, List, Dict

from backend.player import Player

MPRIS_OBJECT_PATH = "/org/mpris/MediaPlayer2"
MPRIS_BUS_NAME = "org.mpris.MediaPlayer2.nami"

PLAYER_STATUS_MAP = {"playing": "Playing", "paused": "Paused", "stopped": "Stopped"}


# ── File metadata helpers ──────────────────────────────────────────────

_mpris_art_cache: dict[str, str | None] = {}


def _find_art(path: str) -> str | None:
    """Find album art for a music file (cached)."""
    if path in _mpris_art_cache:
        return _mpris_art_cache[path]
    try:
        from mutagen import File as MFile
        f = MFile(path)
        if f and hasattr(f, "pictures") and f.pictures:
            import base64
            pic = f.pictures[0]
            b64 = base64.b64encode(pic.data).decode()
            data_uri = f"data:{pic.mime};base64,{b64}"
            _mpris_art_cache[path] = data_uri
            return data_uri
    except Exception:
        pass
    d = Path(path).parent
    for name in ("cover.jpg", "cover.png", "folder.jpg", "front.jpg", "Cover.jpg"):
        cover = d / name
        if cover.exists():
            uri = "file://" + quote(str(cover.resolve()))
            _mpris_art_cache[path] = uri
            return uri
    _mpris_art_cache[path] = None
    return None


def _get_metadata(path: str) -> dict:
    """Return MPRIS metadata dict for a music file."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        from mutagen import mp3
        from mutagen.easyid3 import EasyID3

        p = Path(path).resolve()
        uri = "file://" + quote(str(p))

        metadata = mp3.MP3(path)
        info = EasyID3(path)

        length = int(metadata.info.length * 1_000_000)
        title = info.get("title", [p.stem])[0]
        artist = info.get("artist", ["Unknown"])[0]
        album = info.get("album", [""])[0]
        art_url = _find_art(path)

        meta: dict = {
            "mpris:trackid": ObjPath("/org/nami/track/0"),
            "mpris:length": Int64(length),
            "xesam:title": title,
            "xesam:artist": [artist],
            "xesam:album": album,
            "xesam:url": uri,
        }
        if art_url:
            meta["mpris:artUrl"] = art_url
        return meta
    except Exception:
        return {}


# ── Manual D-Bus introspection XML ─────────────────────────────────────

MPRIS_XML = """<!DOCTYPE node PUBLIC '-//freedesktop//DTD D-BUS Object Introspection 1.0//EN'
  'http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd'>
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="CanSetFullscreen" type="b" access="read"/>
    <property name="Fullscreen" type="b" access="readwrite"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek">
      <arg direction="in" name="Offset" type="x"/>
    </method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId" type="o"/>
      <arg direction="in" name="Position" type="x"/>
    </method>
    <method name="OpenUri">
      <arg direction="in" name="Uri" type="s"/>
    </method>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="LoopStatus" type="s" access="readwrite"/>
    <property name="Rate" type="d" access="read"/>
    <property name="Shuffle" type="b" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
    <signal name="Seeked">
      <arg name="Position" type="x"/>
    </signal>
  </interface>
</node>"""


class MprisMediaPlayer2:
    """Implements both MPRIS 2.1 interfaces on one object path."""

    __dbus_xml__ = MPRIS_XML

    # Signal definitions (connected by dasbus framework)
    PropertiesChanged = Signal()
    Seeked = Signal()

    def __init__(self, player: Player):
        self._player = player
        self._last_status: str | None = None
        self._last_track: str | None = None
        self._last_volume: float = -1
        self._last_shuffle: bool | None = None
        self._last_repeat: bool | None = None
        self._poll_id: int | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start_polling(self):
        self._poll_id = GLib.timeout_add(800, self._poll)

    def stop_polling(self):
        if self._poll_id is not None:
            GLib.source_remove(self._poll_id)
            self._poll_id = None

    def _poll(self) -> bool:
        try:
            self._check_properties()
        except Exception:
            pass
        return True

    def _check_properties(self):
        player = self._player
        if not player.current_music:
            return

        status = PLAYER_STATUS_MAP.get(player.status, "Stopped")
        volume = player._volume / 100.0
        shuffle = player._shuffle
        repeat = player._repeat
        track = player.current_music

        changes = {}
        invalidated = []

        if track != self._last_track or status != self._last_status:
            meta = _get_metadata(track)
            changes["Metadata"] = meta
            changes["PlaybackStatus"] = status
            self._last_track = track

        if status != self._last_status and "PlaybackStatus" not in changes:
            changes["PlaybackStatus"] = status
        self._last_status = status

        if abs(volume - self._last_volume) > 0.01:
            changes["Volume"] = volume
        self._last_volume = volume

        if shuffle != self._last_shuffle:
            changes["Shuffle"] = shuffle
        self._last_shuffle = shuffle

        loop = "Playlist" if repeat else "None"
        if repeat != self._last_repeat:
            changes["LoopStatus"] = loop
        self._last_repeat = repeat

        if changes:
            self.PropertiesChanged(
                "org.mpris.MediaPlayer2.Player",
                changes,
                invalidated,
            )

    # ── org.mpris.MediaPlayer2 root interface ─────────────────────────

    def Raise(self):
        pass

    def Quit(self):
        pass

    @property
    def Identity(self) -> str:
        return "Nami"

    @property
    def DesktopEntry(self) -> str:
        return "nami"

    @property
    def SupportedUriSchemes(self) -> list:
        return ["file"]

    @property
    def SupportedMimeTypes(self) -> list:
        return ["audio/mpeg", "audio/flac", "audio/ogg", "audio/x-m4a", "audio/aac", "audio/wav"]

    @property
    def HasTrackList(self) -> bool:
        return False

    @property
    def CanQuit(self) -> bool:
        return True

    @property
    def CanRaise(self) -> bool:
        return False

    @property
    def CanSetFullscreen(self) -> bool:
        return False

    @property
    def Fullscreen(self) -> bool:
        return False

    @Fullscreen.setter
    def Fullscreen(self, value: bool):
        pass

    # ── org.mpris.MediaPlayer2.Player interface ──────────────────────

    def Play(self):
        self._player.play()

    def Pause(self):
        self._player.pause()

    def PlayPause(self):
        self._player.toggle()

    def Stop(self):
        self._player.stop()

    def Next(self):
        self._player.next()

    def Previous(self):
        self._player.previous()

    def Seek(self, offset: int):
        """Seek by offset microseconds (can be negative)."""
        self._player.forward(int(offset / 1000))
        pos = self._player.player.get_time() if self._player.player else -1
        if pos >= 0:
            self.Seeked(pos * 1000)

    def SetPosition(self, track_id: str, position: int):
        """Set position in microseconds."""
        self._player.seek_to(position / 1_000_000 / self._get_duration_sec() * 100)
        pos = self._player.player.get_time() if self._player.player else -1
        if pos >= 0:
            self.Seeked(pos * 1000)

    def OpenUri(self, uri: str):
        if uri.startswith("file://"):
            path = uri[7:]
            self._player.load(path)
            self._player.play()

    # ── Properties ────────────────────────────────────────────────────

    @property
    def PlaybackStatus(self) -> str:
        return PLAYER_STATUS_MAP.get(self._player.status, "Stopped")

    @property
    def LoopStatus(self) -> str:
        return "Playlist" if self._player._repeat else "None"

    @LoopStatus.setter
    def LoopStatus(self, value: str):
        if value in ("Playlist", "Track"):
            if not self._player._repeat:
                self._player.toggle_repeat()
        else:
            if self._player._repeat:
                self._player.toggle_repeat()

    @property
    def Rate(self) -> float:
        return 1.0

    @property
    def Shuffle(self) -> bool:
        return self._player._shuffle

    @Shuffle.setter
    def Shuffle(self, value: bool):
        if value != self._player._shuffle:
            self._player.toggle_shuffle()

    @property
    def Metadata(self) -> dict:
        return _get_metadata(self._player.current_music)

    @property
    def Volume(self) -> float:
        return self._player._volume / 100.0

    @Volume.setter
    def Volume(self, value: float):
        self._player.set_volume(int(value * 100))

    @property
    def Position(self) -> int:
        pos = self._player.player.get_time() if self._player.player else -1
        return pos * 1000 if pos >= 0 else 0

    @property
    def MinimumRate(self) -> float:
        return 1.0

    @property
    def MaximumRate(self) -> float:
        return 1.0

    @property
    def CanGoNext(self) -> bool:
        return bool(self._player._playlist)

    @property
    def CanGoPrevious(self) -> bool:
        return bool(self._player._playlist)

    @property
    def CanPlay(self) -> bool:
        return self._player.current_music is not None

    @property
    def CanPause(self) -> bool:
        return self._player.current_music is not None

    @property
    def CanSeek(self) -> bool:
        return self._player.current_music is not None

    @property
    def CanControl(self) -> bool:
        return True

    def _get_duration_sec(self) -> float:
        if self._player.player:
            d = self._player.player.get_length()
            if d > 0:
                return d / 1000.0
        return 1.0


# ── Runner ──────────────────────────────────────────────────────────────


class MprisRunner:
    """Manages the MPRIS D-Bus service in a background thread."""

    def __init__(self, player: Player):
        self._player = player
        self._loop: EventLoop | None = None
        self._thread: threading.Thread | None = None
        self._mpris: MprisMediaPlayer2 | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        loop = EventLoop()
        bus = SessionMessageBus()
        try:
            bus.register_service(MPRIS_BUS_NAME)
        except Exception as e:
            print(f"MPRIS: failed to register bus name: {e}")
            return

        mpris = MprisMediaPlayer2(self._player)
        self._mpris = mpris

        bus.publish_object(MPRIS_OBJECT_PATH, mpris)
        mpris.start_polling()

        try:
            loop.run()
        finally:
            mpris.stop_polling()
            bus.unpublish_object(MPRIS_OBJECT_PATH)
