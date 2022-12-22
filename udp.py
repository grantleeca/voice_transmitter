import logging
import socket
import socketserver
import time

from protocol import ProtocolUDP
from stream_thread import StreamThread, InputThread


class UDPReceiver(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, **kwargs):
        s.settimeout(3.0)
        super().__init__(logger, ProtocolUDP(s, address))

        self.stream = self.open_stream(output=True, **kwargs)


class UDPSender(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, chunk, **kwargs):
        super().__init__(logger, ProtocolUDP(s, address))

        self._chunk = chunk
        self.stream = self.open_stream(input=True, frames_per_buffer=chunk, **kwargs)


class UDPHandler(socketserver.BaseRequestHandler):
    logger = None

    def handle(self):
        self.logger.info(f"{self.client_address} linked.")

        ptc = ProtocolUDP(self.request[1], self.client_address, self.request[0])
        request = ptc.verify()
        if isinstance(request, tuple):
            args = {'format': request[0], 'channels': request[1], 'rate': request[2]}
            self.logger.info(f"Service information: {args}.")

            receiver = UDPReceiver(self.logger, self.request[1], self.client_address, **args)
            sender = UDPSender(self.logger, self.request[1], self.client_address, chunk=request[3], **args)

            receiver.start()
            sender.start()

            receiver.join()
            sender.join()

        else:
            self.logger.info(request)


class UDPClient(ProtocolUDP):
    def __init__(self, logger, address):
        super().__init__(socket.socket(socket.AF_INET, socket.SOCK_DGRAM), address)

        self._logger = logger

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self, chunk, **kwargs):
        self._logger.info(f"Connected {self._address}.")

        res = self.login(chunk=chunk, **kwargs)
        if res == 'OK':
            receiver = UDPReceiver(self._logger, self._socket, self._address)
            sender = UDPSender(self._logger, self._socket, self._address, chunk=chunk)
            input_key = InputThread()

            receiver.start()
            sender.start()
            input_key.start()

            while receiver.is_alive() and sender.is_alive() and input_key.is_alive():
                time.sleep(1)

            StreamThread.stop = True

            receiver.join()
            sender.join()

        else:
            self._logger.warning(f'Login failed. {res}')

