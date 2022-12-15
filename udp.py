import logging
import socket
import socketserver
import struct

from stream_thread import StreamThread, HEAD_FORMAT, HEAD_VERSION, CHUNK


class UDPReceiver(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, **kwargs):
        super().__init__(logger)

        self._socket = s
        self._address = address
        self.stream = self.open_stream(output=True, **kwargs)

    def run(self):
        try:
            self._socket.settimeout(3.0)

            while self.running:
                response = self._socket.recvfrom(8192)
                if self._address != response[1]:
                    self._logger.warning(f'Address wrong: {self._address}: {response[1]}')
                self.stream.write(response[0])

            self._logger.info('Voice receiver finished.')

        except Exception as e:
            self._logger.info(f'recv error, disconnect. {type(e)}: {str(e)}')

        finally:
            self._socket.settimeout(None)


class UDPSender(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, chunk, **kwargs):
        super().__init__(logger)

        self._chunk = chunk
        self._socket = s
        self._address = address
        self.stream = self.open_stream(input=True, frames_per_buffer=chunk, **kwargs)

    def run(self):
        try:
            while self.running:
                self._socket.sendto(self.stream.read(self._chunk), self._address)

            self._logger.info('Voice sender finished.')

        except ConnectionError:
            self._logger.info('Sendto error, disconnect.')


class UDPHandler(socketserver.BaseRequestHandler):
    logger = None

    def recv_head(self):
        data = self.request[0]
        return struct.unpack(HEAD_FORMAT, data) if len(data) == struct.calcsize(HEAD_FORMAT) else None

    def send_reply(self, msg):
        self.request[1].sendto(msg.encode('utf-8'), self.client_address)

    def handle(self):
        request = self.recv_head()
        if request is None:
            self.logger.debug('Invalid request.')
            return

        if request[0] != HEAD_VERSION:
            self.logger.debug('invalid protocol or version.')
            return

        self.send_reply('OK')

        args = {'format': request[1],
                'channels': request[2],
                'rate': request[3]}

        self.logger.info(f"Service information: {args}.")

        with UDPSender(self.logger, self.request[1], self.client_address, **args) as client, \
                UDPReceiver(self.logger, self.request[1], self.client_address, **args) as server:
            server.start()
            client.start()

            server.join()

            client.finish()
            client.join()


class UDPClient:
    def __init__(self, logger):
        self._logger = logger
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._socket.close()
        self._socket = None

    def login(self, addr, format, channels, rate):
        data = struct.pack(HEAD_FORMAT, HEAD_VERSION, format, channels, rate)
        self._socket.sendto(data, addr)
        response = self._socket.recvfrom(1024)
        if response[0].decode('utf-8') != 'OK':
            self._logger.warning(f'Unknown response: {response}')
            return False

        return True

    def udp_start(self, addr, **kwargs):
        self._logger.info(f"Connected {addr}.")

        if not self.login(addr, **kwargs):
            self._logger.warning(f'Login failed.')
            return

        with UDPReceiver(self._logger, self._socket, addr) as server, UDPSender(self._logger, self._socket, addr,
                                                                                chunk=CHUNK) as client:
            server.start()
            client.start()

            input("Press enter key to exit.")

            client.finish()
            client.join()

            server.finish()
            server.join()
