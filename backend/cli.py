import socket
import sys
import threading
import json

HOST, PORT = "127.0.0.1", 20150


class RequestBuilder:
    @staticmethod
    def play():
        return {"request": "play", "params": {}}

    @staticmethod
    def pause():
        return {"request": "pause", "params": {}}

    @staticmethod
    def stop():
        return {"request": "stop", "params": {}}

    @staticmethod
    def toggle():
        return {"request": "toggle", "params": {}}

    @staticmethod
    def info():
        return {"request": "info", "params": {}}

    @staticmethod
    def position():
        return {"request": "position", "params": {}}

    @staticmethod
    def state():
        return {"request": "state", "params": {}}

    @staticmethod
    def forward(seconds: int = 5):
        return {"request": "forward", "params": {"seconds": seconds}}

    @staticmethod
    def backward(seconds: int = 5):
        return {"request": "backward", "params": {"seconds": seconds}}

    @staticmethod
    def seek_to(position: float):
        return {"request": "seek_to", "params": {"position": position}}

    @staticmethod
    def volume(vol: int):
        return {"request": "volume", "params": {"volume": vol}}

    @staticmethod
    def load(path: str):
        return {"request": "load", "params": {"path": path}}

    @staticmethod
    def next():
        return {"request": "next", "params": {}}

    @staticmethod
    def previous():
        return {"request": "previous", "params": {}}

    @staticmethod
    def add_to_playlist(path: str):
        return {"request": "add_to_playlist", "params": {"path": path}}

    @staticmethod
    def get_playlist():
        return {"request": "get_playlist", "params": {}}

    @staticmethod
    def shuffle():
        return {"request": "shuffle", "params": {}}

    @staticmethod
    def repeat():
        return {"request": "repeat", "params": {}}


def send_message(sock, data):
    payload = json.dumps(data).encode() + b"\n"
    sock.sendall(payload)


def recv_message(sock):
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        buf += chunk
    line, _ = buf.split(b"\n", 1)
    return json.loads(line)


def receive_loop(sock):
    while True:
        response = recv_message(sock)
        if response is None:
            print("\n[Client] Disconnected from server.")
            break
        print(f"\n[Response] {json.dumps(response, indent=2)}")
        print("Enter command: ", end="", flush=True)


HELP = """Commands:
  play / pause / stop / toggle   Playback control
  info                           Show track metadata
  position                       Show current position
  state                          Show player state
  fwd [sec]                      Seek forward (default 5s)
  bwd [sec]                      Seek backward (default 5s)
  seek <pct>                     Seek to percentage (0-100)
  vol <0-150>                    Set volume
  load <path>                    Load a file
  next / prev                    Navigate playlist
  add <path>                     Add to playlist
  playlist                       Show playlist
  shuffle / repeat               Toggle modes
  quit                           Exit
"""


def main():
    print(f"[Client] Connecting to Nami server at {HOST}:{PORT}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, PORT))
    except ConnectionRefusedError:
        print("[Error] Could not connect. Is backend/server.py running?")
        sys.exit(1)

    print("[Client] Connected! Type 'help' for commands.")

    thread = threading.Thread(target=receive_loop, args=(s,), daemon=True)
    thread.start()

    while True:
        try:
            inp = input("Enter command: ").strip().lower()
            if not inp:
                continue

            parts = inp.split(maxsplit=1)
            cmd = parts[0]
            arg = parts[1] if len(parts) > 1 else ""

            if cmd in ("quit", "exit"):
                send_message(s, {"request": "disconnect", "params": {}})
                break
            elif cmd == "help":
                print(HELP)
            elif cmd == "play":
                send_message(s, RequestBuilder.play())
            elif cmd == "pause":
                send_message(s, RequestBuilder.pause())
            elif cmd == "stop":
                send_message(s, RequestBuilder.stop())
            elif cmd == "toggle":
                send_message(s, RequestBuilder.toggle())
            elif cmd == "info":
                send_message(s, RequestBuilder.info())
            elif cmd == "position":
                send_message(s, RequestBuilder.position())
            elif cmd == "state":
                send_message(s, RequestBuilder.state())
            elif cmd == "fwd":
                send_message(s, RequestBuilder.forward(int(arg) if arg else 5))
            elif cmd == "bwd":
                send_message(s, RequestBuilder.backward(int(arg) if arg else 5))
            elif cmd == "seek":
                send_message(s, RequestBuilder.seek_to(float(arg)))
            elif cmd == "vol":
                send_message(s, RequestBuilder.volume(int(arg)))
            elif cmd == "load":
                send_message(s, RequestBuilder.load(arg))
            elif cmd == "next":
                send_message(s, RequestBuilder.next())
            elif cmd == "prev":
                send_message(s, RequestBuilder.previous())
            elif cmd == "add":
                send_message(s, RequestBuilder.add_to_playlist(arg))
            elif cmd == "playlist":
                send_message(s, RequestBuilder.get_playlist())
            elif cmd == "shuffle":
                send_message(s, RequestBuilder.shuffle())
            elif cmd == "repeat":
                send_message(s, RequestBuilder.repeat())
            else:
                print(f"Unknown command: {cmd}. Type 'help' for options.")

        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            print(f"[Error] {e}")
            break

    s.close()
    print("[Client] Closed.")


if __name__ == "__main__":
    main()
