import logging
import socket
import socketserver
import struct

from stream_thread import StreamThread, HEAD_FORMAT, CHUNK


class TCPReceiver(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, **kwargs):
        super().__init__(logger)

        self.socket = s
        self.stream = self.open_stream(output=True, **kwargs)

    def run(self):
        try:
            self.socket.settimeout(3.0)
            while self.running:
                response = self.socket.recv(8192)
                self.stream.write(response)

            self._logger.info('Voice server finished.')

        except Exception as e:
            self._logger.info(f'recv error, disconnect. {type(e)}: {str(e)}')

        finally:
            self.socket.settimeout(None)


class TCPSender(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, chunk, **kwargs):
        super().__init__(logger)

        self._chunk = chunk
        self._socket = s
        self.stream = self.open_stream(input=True, frames_per_buffer=chunk, **kwargs)

    def run(self):
        try:
            while self.running:
                self._socket.send(self.stream.read(self._chunk))

            self._logger.info('Voice sender finished.')

        except ConnectionError:
            self._logger.info('Sendto error, disconnect.')


class TCPHandler(socketserver.BaseRequestHandler):
    logger = logging.getLogger(__name__)

    def recv_head(self):
        buf = self.request.recv(1024)
        return struct.unpack(HEAD_FORMAT, buf) if len(buf) == struct.calcsize(HEAD_FORMAT) else None

    def send_reply(self, msg: str):
        self.request.sendall(msg.encode('utf-8'))

    def handle(self):
        self.logger.info(f"{self.client_address} linked.")

        request = self.recv_head()
        if request is None:
            self.logger.debug('Invalid request.')
            return

        if request[0] != 'AudioTransmitter 001':
            self.logger.debug('invalid protocol or version.')
            return

        self.send_reply('OK')

        args = {'format': request[1],
                'channels': request[2],
                'rate': request[3]}

        self.logger.info(f"Service information: {args}.")

        with TCPSender(self.logger, self.request, chunk=CHUNK, **args) as client, \
                TCPReceiver(self.logger, self.request, **args) as server:
            server.start()
            client.start()

            server.join()

            client.finish()
            client.join()


class TCPClient:
    def __init__(self, logger):
        self._logger = logger
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._socket.close()
        self._socket = None

    def login(self, format, channels, rate):
        data = struct.pack(HEAD_FORMAT, 'AudioTransmitter 001', format, channels, rate)
        self._socket.sendall(data)

        data = self._socket.recv(1024)
        return True if data.strip().decode('utf-8') == 'OK' else False

    def connect(self, addr, **kwargs):
        self._logger.debug(f"Begin connect to {addr}")

        self._socket.connect(addr)

        self._logger.info(f"Connected {addr}.")

        if not self.login(**kwargs):
            self._logger.warning(f'Login failed.')
            return

        with TCPReceiver(self._logger, self._socket) as server, \
                TCPSender(self._logger, self._socket, chunk=CHUNK) as client:
            server.start()
            client.start()

            input("Press enter key to exit.")

            client.finish()
            server.finish()

            client.join()
            server.join()
