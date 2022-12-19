import logging
import socket
import socketserver

from protocol import ProtocolUDP
from stream_thread import StreamThread


class UDPReceiver(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, **kwargs):
        s.settimeout(3.0)
        super().__init__(logger, ProtocolUDP(address, s))

        self.stream = self.open_stream(output=True, **kwargs)


class UDPSender(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, chunk, **kwargs):
        super().__init__(logger, ProtocolUDP(address, s))

        self._chunk = chunk
        self.stream = self.open_stream(input=True, frames_per_buffer=chunk, **kwargs)


class UDPHandler(socketserver.BaseRequestHandler):
    logger = None

    def handle(self):
        self.logger.info(f"{self.client_address} linked.")

        ptc = ProtocolUDP(self.request)
        request = ptc.verify()
        if isinstance(request, tuple):
            args = {'format': request[0],
                    'channels': request[1],
                    'rate': request[2]}

            self.logger.info(f"Service information: {args}.")

            with UDPSender(self.logger, self.request[1], self.client_address, chunk=request[3], **args) as client, \
                    UDPReceiver(self.logger, self.request[1], self.client_address, **args) as server:
                server.start()
                client.start()

                server.join()
                client.join()

        else:
            self.logger.info(request)


class UDPClient(ProtocolUDP):
    def __init__(self, logger, address):
        super().__init__(address, socket.socket(socket.AF_INET, socket.SOCK_DGRAM))

        self._logger = logger

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._socket.close()
        self._socket = None

    def connect(self, chunk, **kwargs):
        self._logger.info(f"Connected {self._address}.")

        if not self.login(chunk=chunk, **kwargs):
            self._logger.warning(f'Login failed.')
            return

        with UDPReceiver(self._logger, self._socket, self._address) as server, \
                UDPSender(self._logger, self._socket, self._address, chunk=chunk) as client:
            server.start()
            client.start()

            input("Press enter key to exit.")
            self.close()

            client.join()
            server.join()
