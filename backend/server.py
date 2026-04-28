import socket

class Mint:
    def __init__(self,host='127.0.0.1',port=13283) -> None:
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        print(f"Server initialzied on {host}:{port}")
    
    def start(self):
        self.socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host,self.port))
        self.socket.listen(1)
        self.running = True

    def process_client(self):
        conn,addr = self.socket.accept()
        with conn:
            while self.running:
                data = conn.recv(1024)
                if 'break' in data.decode('utf-8'):
                    self.close()
                if 'disconnect' in data.decode('utf-8'):
                    conn.close()
                if 'stop' in data.decode('utf-8'):
                    break

                print(data)
            
    
    def close(self):
        self.running = False


server = Mint()

server.start()

