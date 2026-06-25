import socket
import json
from backend.player import Player


class Mint:
    def __init__(self, host="127.0.0.1", port=20150, player=None, database=None) -> None:
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.player = player or Player()
        self.database = database
        self.commands = {
            "play": lambda _: self.player.play(),
            "pause": lambda _: self.player.pause(),
            "stop": lambda _: self.player.stop(),
            "toggle": lambda _: self.player.toggle(),
            "info": lambda _: self.player.get_info(),
            "position": lambda _: self.player.get_position(),
            "state": lambda _: self.player.get_state(),
            "forward": lambda p: self.player.forward(p.get("seconds", 5)),
            "backward": lambda p: self.player.backward(p.get("seconds", 5)),
            "seek_to": lambda p: self.player.seek_to(p.get("position", 0)),
            "volume": lambda p: self.player.set_volume(p.get("volume", 100)),
            "get_volume": lambda _: self.player.get_volume(),
            "load": lambda p: self.player.load(p["path"]) or {"status": "loaded"},
            "next": lambda _: self.player.next(),
            "previous": lambda _: self.player.previous(),
            "add_to_playlist": lambda p: self.player.add_to_playlist(p["path"]),
            "remove_from_playlist": lambda p: self.player.remove_from_playlist(
                p["index"]
            ),
            "get_playlist": lambda _: self.player.get_playlist(),
            "clear_playlist": lambda _: self.player.clear_playlist(),
            "play_index": lambda p: self.player.play_index(p["index"]),
            "shuffle": lambda _: self.player.toggle_shuffle(),
            "repeat": lambda _: self.player.toggle_repeat(),
        }
        if database:
            self.commands["database_list"] = lambda _: {
                "music": database.read_db_all()
            }
            self.commands["database_search"] = lambda p: {
                "music": [
                    m.to_dict()
                    for m in database.search(
                        p.get("field", "title"), p.get("query", "")
                    )
                ]
            }
            self.commands["database_refresh"] = lambda _: (
                database.init_db() or {"status": "refreshed"}
            )

    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        self.running = True
        print(f"Server listening on {self.host}:{self.port}")

    def process_requests(self):
        while self.running:
            conn, addr = self.socket.accept()
            with conn:
                print(f"Client connected: {addr}")
                self._handle_connection(conn)

    def _handle_connection(self, conn: socket.socket):
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                response = self._dispatch(line)
                conn.sendall(json.dumps(response).encode() + b"\n")

    def _dispatch(self, raw: bytes) -> dict:
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            return {"error": "invalid json"}

        command = req.get("request")
        params = req.get("params", {})

        handler = self.commands.get(command)
        if handler is None:
            return {"error": f"unknown command: {command}"}

        try:
            return handler(params)
        except Exception as e:
            return {"error": str(e)}

    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()
