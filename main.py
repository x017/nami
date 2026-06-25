import json
import os
from pathlib import Path

from backend.database.database import Database
from backend.server import Mint

CONFIG_DIR = Path.home() / ".config" / "nami"
CONFIG_PATH = CONFIG_DIR / "config.json"

if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
else:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {
        "port": 20224,
        "music_path": str(Path.home() / "Music"),
        "db_path": str(CONFIG_DIR / "db.json"),
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2))

def main():
    port = config["port"]
    music_path = config["music_path"]
    db_path = config["db_path"]
    db = Database(db_path=db_path, music_path=music_path)
    db.init_db()
    all_music = db.read_db_all()
    print(f"Database has {len(all_music)} entries")
    server = Mint(port=port, database=db)
    server.start()
    server.process_requests()


if __name__ == "__main__":
    main()
