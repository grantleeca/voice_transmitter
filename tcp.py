import logging
import socket
import socketserver
import struct
import time

from stream_thread import StreamThread, HEAD_FORMAT, HEAD_VERSION


class TCPReceiver(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, **kwargs):
        super().__init__(logger)

        logger.debug(f'init parameter: {kwargs}')
        self.socket = s
        self.stream = self.open_stream(output=True, **kwargs)

    def run(self):
        try:
            start_time = time.perf_counter()
            count = 0

            self.socket.settimeout(3.0)
            while True:
                response = self.socket.recv(8192)
                self.stream.write(response)

                count += len(response)
                end_time = time.perf_counter()
                if end_time - start_time > 1.0:
                    self._logger.info(f"Receiver speed: {count / 1024 / (end_time - start_time): .2f} KB/s.")
                    start_time = end_time
                    count = 0

        except Exception as e:
            self._logger.debug(f'Voice receiver disconnect. {type(e)}: {str(e)}')

        finally:
            self.socket.close()
            self._logger.info('Voice receiver disconnect')


class TCPSender(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, chunk, **kwargs):
        super().__init__(logger)

        self._chunk = chunk
        self._socket = s
        self.stream = self.open_stream(input=True, frames_per_buffer=chunk, **kwargs)

    def run(self):
        try:
            while True:
                self._socket.send(self.stream.read(self._chunk))

        except Exception as e:
            self._logger.debug(f'Voice sender disconnect. {type(e)}: {str(e)}')

        finally:
            self._socket.close()
            self._logger.info('Voice sender disconnected.')


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
            self.send_reply('Invalid request.')
            self.logger.debug('Invalid request.')
            return

        if request[0] != HEAD_VERSION:
            self.send_reply('Invalid protocol or version')
            self.logger.debug(f'invalid protocol or version.: {request[0]}.')
            return

        self.send_reply('OK')

        args = {'format': request[1],
                'channels': request[2],
                'rate': request[3]}

        self.logger.info(f"Service information: {args}.")

        with TCPSender(self.logger, self.request, chunk=request[4], **args) as client, \
                TCPReceiver(self.logger, self.request, **args) as server:
            server.start()
            client.start()

            server.join()
            client.join()


class TCPClient:
    def __init__(self, logger: logging.Logger):
        self._logger = logger
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._socket.close()
        self._socket = None

    def login(self, format, channels, rate, chunk):
        data = struct.pack(HEAD_FORMAT, HEAD_VERSION, format, channels, rate, chunk)
        self._socket.sendall(data)

        self._socket.settimeout(None)
        data = self._socket.recv(1024)
        self._logger.debug(f'Login return {data}')
        return True if data.strip().decode('utf-8') == 'OK' else False

    def connect(self, addr, chunk, **kwargs):
        self._logger.debug(f"Begin connect to {addr}")

        self._socket.connect(addr)

        self._logger.info(f"Connected {addr}.")

        if not self.login(chunk=chunk, **kwargs):
            self._logger.warning(f'Login failed.')
            return

        with TCPReceiver(self._logger, self._socket, **kwargs) as server, \
                TCPSender(self._logger, self._socket, chunk=chunk, **kwargs) as client:
            server.start()
            client.start()

            input("Press enter key to exit.")
            self._socket.close()

            client.join()
            server.join()
