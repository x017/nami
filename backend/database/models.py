from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Music:
    id: str
    title: str
    path: str
    artist: str = "Unknown"
    album: str = "Unknown"
    genre: str = "Unknown"
    date: str = "Unknown"
    length: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "artist": self.artist,
            "album": self.album,
            "genre": self.genre,
            "date": self.date,
            "length": self.length,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Music:
        return cls(
            id=data["id"],
            title=data.get("title", data["path"]),
            path=data["path"],
            artist=data.get("artist", "Unknown"),
            album=data.get("album", "Unknown"),
            genre=data.get("genre", "Unknown"),
            date=data.get("date", "Unknown"),
            length=data.get("length", 0.0),
        )


class Playlist:
    def __init__(self) -> None:
        self._items: list[Music] = []
        self._current_index: int = -1
        self._shuffle: bool = False
        self._repeat: bool = False

    @property
    def items(self) -> list[Music]:
        return list(self._items)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def current(self) -> Optional[Music]:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return None

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat(self) -> bool:
        return self._repeat

    def add(self, music: Music) -> None:
        self._items.append(music)

    def remove(self, index: int) -> Optional[Music]:
        if not 0 <= index < len(self._items):
            return None
        removed = self._items.pop(index)
        if self._current_index >= len(self._items):
            self._current_index = len(self._items) - 1
        return removed

    def clear(self) -> None:
        self._items.clear()
        self._current_index = -1

    def play_index(self, index: int) -> Optional[Music]:
        if not 0 <= index < len(self._items):
            return None
        self._current_index = index
        return self._items[index]

    def next(self) -> Optional[Music]:
        if not self._items:
            return None
        next_idx = self._current_index + 1
        if next_idx >= len(self._items):
            if self._repeat:
                next_idx = 0
            else:
                return None
        self._current_index = next_idx
        return self._items[next_idx]

    def previous(self) -> Optional[Music]:
        if not self._items:
            return None
        prev_idx = self._current_index - 1
        if prev_idx < 0:
            if self._repeat:
                prev_idx = len(self._items) - 1
            else:
                return None
        self._current_index = prev_idx
        return self._items[prev_idx]

    def toggle_shuffle(self) -> bool:
        self._shuffle = not self._shuffle
        return self._shuffle

    def toggle_repeat(self) -> bool:
        self._repeat = not self._repeat
        return self._repeat
