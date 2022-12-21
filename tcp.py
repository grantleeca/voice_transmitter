import logging
import socket
import socketserver

from protocol import ProtocolTCP
from stream_thread import StreamThread


class TCPReceiver(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, **kwargs):
        super().__init__(logger, ProtocolTCP(s))

        self.stream = self.open_stream(output=True, **kwargs)


class TCPSender(StreamThread):
    def __init__(self, logger: logging.Logger, s: socket.socket, chunk, **kwargs):
        super().__init__(logger, ProtocolTCP(s))

        self._chunk = chunk
        self.stream = self.open_stream(input=True, frames_per_buffer=chunk, **kwargs)


class TCPHandler(socketserver.BaseRequestHandler):
    logger = logging.getLogger(__name__)

    def handle(self):
        self.logger.info(f"{self.client_address} linked.")

        ptc = ProtocolTCP(self.request)
        request = ptc.verify()
        if isinstance(request, tuple):
            args = {'format': request[0], 'channels': request[1], 'rate': request[2]}
            self.logger.info(f"Service information: {args}.")

            receiver = TCPReceiver(self.logger, self.request, **args)
            sender = TCPSender(self.logger, self.request, chunk=request[3], **args)

            receiver.start()
            sender.start()

            receiver.join()
            sender.join()

        else:
            self.logger.info(request)


class TCPClient(ProtocolTCP):
    def __init__(self, logger: logging.Logger):
        self._logger = logger
        super().__init__(socket.socket(socket.AF_INET, socket.SOCK_STREAM))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self, addr, chunk, **kwargs):
        self._logger.debug(f"Begin connect to {addr}")

        self._socket.connect(addr)

        self._logger.info(f"Connected {addr}.")

        res = self.login(chunk=chunk, **kwargs)
        if res != 'OK':
            self._logger.warning(f'Login failed.: {res}')
            return

        receiver = TCPReceiver(self._logger, self._socket, **kwargs)
        sender = TCPSender(self._logger, self._socket, chunk=chunk, **kwargs)

        receiver.start()
        sender.start()

        input("Press enter key to exit.")
        self._socket.close()

        receiver.join()
        sender.join()
