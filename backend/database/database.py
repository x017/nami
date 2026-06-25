from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from mutagen import File
from tinydb import Query, TinyDB

from backend.database.models import Music

AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".wma"}


class Database:
    def __init__(self, db_path: str, music_path: str) -> None:
        self.db_path = db_path
        self.music_path = Path(music_path)
        self.db = TinyDB(db_path)

    def _scan_files(self) -> list[Path]:
        files: list[Path] = []
        if not self.music_path.is_dir():
            return files
        for entry in self.music_path.rglob("*"):
            if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS:
                files.append(entry)
        return files

    @staticmethod
    def _path_id(path: Path) -> str:
        return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]

    def _music_from_file(self, path: Path) -> Optional[Music]:
        try:
            audio = File(path)
        except Exception:
            return None

        if audio is None or audio.tags is None:
            return None

        return Music(
            id=self._path_id(path),
            title=_tag_value(audio.tags, "title", path.stem),
            path=str(path.resolve()),
            artist=_tag_value(audio.tags, "artist", "Unknown"),
            album=_tag_value(audio.tags, "album", "Unknown"),
            genre=_tag_value(audio.tags, "genre", "Unknown"),
            date=_tag_value(audio.tags, "date", "Unknown"),
            length=round(audio.info.length, 2) if getattr(audio.info, "length", None) else 0.0,
        )

    def _existing_paths(self) -> set[str]:
        return {doc["path"] for doc in self.db.all()}

    def init_db(self) -> None:
        existing_paths = self._existing_paths()
        entries: list[dict] = []
        for path in self._scan_files():
            resolved = str(path.resolve())
            if resolved in existing_paths:
                continue
            music = self._music_from_file(path)
            if music is not None:
                entries.append(music.to_dict())
        if entries:
            self.db.insert_multiple(entries)

    def read_db_all(self) -> list[dict]:
        return self.db.all()

    def update_db(self) -> None:
        current_files = {str(p.resolve()) for p in self._scan_files()}
        existing_docs = self.db.all()

        MusicQuery = Query()
        to_remove_ids = [
            doc.doc_id for doc in existing_docs if doc["path"] not in current_files
        ]
        if to_remove_ids:
            self.db.remove(doc_ids=to_remove_ids)

        existing_paths = {doc["path"] for doc in self.db.all()}
        entries: list[dict] = []
        for path in self._scan_files():
            resolved = str(path.resolve())
            if resolved in existing_paths:
                continue
            music = self._music_from_file(path)
            if music is not None:
                entries.append(music.to_dict())
        if entries:
            self.db.insert_multiple(entries)

    def get_music(self, music_id: str) -> Optional[Music]:
        MusicQuery = Query()
        results = self.db.search(MusicQuery.id == music_id)
        if not results:
            return None
        return Music.from_dict(results[0])

    def search(self, field: str = "title", query: str = "") -> list[Music]:
        MusicQuery = Query()
        results = self.db.search(MusicQuery[field].search(query, flags=0))
        return [Music.from_dict(doc) for doc in results]

    def close(self) -> None:
        self.db.close()


def _tag_value(tags, key: str, default: str) -> str:
    value = tags.get(key)
    if value is None:
        return default
    if isinstance(value, list):
        return value[0] if value else default
    return str(value)
