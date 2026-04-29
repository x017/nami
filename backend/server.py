import socket
import cbor2 as cbor
from player import Player


player = Player()
player.load('test.mp3')

class Mint:
    """
    Mint Server Class
    """
    def __init__(self, host="127.0.0.1", port=20150) -> None:
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        print(f"Server initialzied on {host}:{port}")

    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        self.running = True

    def process_requests(self):
        while self.running:
            conn, addr = self.socket.accept()
            with conn:
                while True:
                    data = conn.recv(1024).decode('utf-8')
                    if not data:
                        break
                    if "disconnect" in data:
                        self.close_connection(conn)
                        break
                    if "play" in data:
                        player.play()
                    if "pause" in data:
                        player.pause()
                    if "info" in data:
                        info = player.get_info()
                        print(info)

    def close_connection(self,connection):
        connection.close()



server = Mint()
server.start()
server.process_requests()
