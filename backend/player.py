import threading
from mutagen.easyid3 import EasyID3
import vlc
from mutagen import mp3


class Player:
    def __init__(self):
        self.current_music = None
        self.player = None
        self.is_playing = threading.Event()
        self.status = "stopped"
        self._playlist: list[str] = []
        self._playlist_index: int = -1
        self._volume: int = 100
        self._shuffle: bool = False
        self._repeat: bool = False

    # ── Playback control ──────────────────────────────────────────────

    def load(self, path: str):
        if self.player:
            self.player.stop()
        self.current_music = path
        self.player = vlc.MediaPlayer(self.current_music)
        events = self.player.event_manager()
        events.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_playback_end)
        self.status = "stopped"

    def play(self):
        if not self.player:
            return {"error": "no media loaded"}
        self.is_playing.set()
        self.player.play()
        self.status = "playing"
        return {"status": "playing"}

    def stop(self):
        if not self.player:
            return {"error": "no media loaded"}
        self.player.stop()
        self.is_playing.clear()
        self.status = "stopped"
        return {"status": "stopped"}

    def pause(self):
        if not self.player:
            return {"error": "no media loaded"}
        if self.player.is_playing():
            self.player.set_pause(1)
            self.is_playing.clear()
            self.status = "paused"
            return {"status": "paused"}
        else:
            self.player.set_pause(0)
            self.is_playing.set()
            self.status = "playing"
            return {"status": "playing"}

    def toggle(self):
        if not self.player:
            return {"error": "no media loaded"}
        if self.status == "playing":
            return self.pause()
        else:
            return self.play()

    # ── Seeking ───────────────────────────────────────────────────────

    def forward(self, seconds: int = 5):
        if not self.player:
            return {"error": "no media loaded"}
        duration = self.player.get_length()
        if duration <= 0:
            return {"error": "duration unknown"}
        current = self.player.get_time()
        if current < 0:
            current = 0
        new_time = min(duration, current + seconds * 1000)
        result = self.player.set_time(int(new_time))
        if result == 0:
            return {"position_ms": int(new_time)}
        return {"error": "seek failed"}

    def backward(self, seconds: int = 5):
        if not self.player:
            return {"error": "no media loaded"}
        duration = self.player.get_length()
        if duration <= 0:
            return {"error": "duration unknown"}
        current = self.player.get_time()
        if current < 0:
            current = 0
        new_time = max(0, current - seconds * 1000)
        result = self.player.set_time(int(new_time))
        if result == 0:
            return {"position_ms": int(new_time)}
        return {"error": "seek failed"}

    def seek_to(self, position_pct: float):
        if not self.player:
            return {"error": "no media loaded"}
        position_pct = max(0.0, min(100.0, position_pct))
        result = self.player.set_position(position_pct / 100.0)
        if result == 0:
            return {"position_pct": position_pct}
        return {"error": "seek failed"}

    # ── Volume ────────────────────────────────────────────────────────

    def set_volume(self, volume: int):
        volume = max(0, min(150, volume))
        self._volume = volume
        if self.player:
            self.player.audio_set_volume(volume)
        return {"volume": volume}

    def get_volume(self):
        return {"volume": self._volume}

    # ── Info / state ──────────────────────────────────────────────────

    def get_info(self):
        if not self.current_music:
            return {"error": "no media loaded"}
        try:
            metadata = mp3.MP3(self.current_music)
            info = EasyID3(self.current_music)
        except Exception:
            return {"error": "could not read metadata"}

        return {
            "title": info.get("title", ["Unknown"])[0],
            "artist": info.get("artist", ["Unknown"])[0],
            "album": info.get("album", ["Unknown"])[0],
            "genre": info.get("genre", ["Unknown"])[0],
            "date": info.get("date", ["Unknown"])[0],
            "length": f"{metadata.info.length:.2f}",
        }

    def get_position(self):
        if not self.player:
            return {"error": "no media loaded"}
        return {
            "position_pct": round(self.player.get_position() * 100, 2),
            "position_ms": self.player.get_time(),
            "duration_ms": self.player.get_length(),
            "status": self.status,
        }

    def get_state(self):
        return {
            "status": self.status,
            "current_music": self.current_music,
            "volume": self._volume,
            "shuffle": self._shuffle,
            "repeat": self._repeat,
            "playlist_index": self._playlist_index,
            "playlist_length": len(self._playlist),
        }

    # ── Playlist / queue ──────────────────────────────────────────────

    def add_to_playlist(self, path: str):
        self._playlist.append(path)
        return {"playlist_length": len(self._playlist)}

    def remove_from_playlist(self, index: int):
        if 0 <= index < len(self._playlist):
            self._playlist.pop(index)
            if self._playlist_index >= len(self._playlist):
                self._playlist_index = len(self._playlist) - 1
            return {"playlist_length": len(self._playlist)}
        return {"error": "index out of range"}

    def get_playlist(self):
        return {
            "playlist": [{"index": i, "path": p} for i, p in enumerate(self._playlist)],
            "current_index": self._playlist_index,
        }

    def clear_playlist(self):
        self._playlist.clear()
        self._playlist_index = -1
        return {"playlist_length": 0}

    def play_index(self, index: int):
        if 0 <= index < len(self._playlist):
            self._playlist_index = index
            self.stop()
            self.load(self._playlist[index])
            return self.play()
        return {"error": "index out of range"}

    def next(self):
        if not self._playlist:
            return {"error": "playlist is empty"}
        next_idx = self._playlist_index + 1
        if next_idx >= len(self._playlist):
            if self._repeat:
                next_idx = 0
            else:
                return {"error": "end of playlist"}
        return self.play_index(next_idx)

    def previous(self):
        if not self._playlist:
            return {"error": "playlist is empty"}
        prev_idx = self._playlist_index - 1
        if prev_idx < 0:
            if self._repeat:
                prev_idx = len(self._playlist) - 1
            else:
                return {"error": "start of playlist"}
        return self.play_index(prev_idx)

    def toggle_shuffle(self):
        self._shuffle = not self._shuffle
        return {"shuffle": self._shuffle}

    def toggle_repeat(self):
        self._repeat = not self._repeat
        return {"repeat": self._repeat}

    # ── Internal ──────────────────────────────────────────────────────

    def _on_playback_end(self, event):
        self.is_playing.clear()
        self.status = "stopped"
        if self._playlist and self._repeat:
            self.next()

    def wait_until_finished(self):
        while self.is_playing.is_set():
            import time

            time.sleep(0.1)
