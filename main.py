import argparse
import logging
import os
import socket
import socketserver
import sys
import threading
from logging.handlers import RotatingFileHandler

import pyaudio

DEFAULT_PORT = 1029

CHUNK = 1024  # 每个缓冲区的帧数
FORMAT = pyaudio.paInt16  # 采样位数
CHANNELS = 1  # 单声道
RATE = 44100  # 采样频率


class AudioTransmitter(threading.Thread):
    pa = None

    @classmethod
    def open_stream(cls, format=None, channels=None, rate=None, **kwargs):
        if cls.pa is None:
            cls.pa = pyaudio.PyAudio()

        return cls.pa.open(format=format if format else FORMAT,
                           channels=channels if channels else CHANNELS,
                           rate=rate if rate else RATE, **kwargs)

    def __init__(self, logger: logging.Logger, s: socket.socket, address):
        super().__init__()

        self._logger = logger
        self._socket = s
        self._address = address

        self.running = True
        self.stream = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

    def finish(self):
        self.running = False


class TransServer(AudioTransmitter):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, **kwargs):
        super().__init__(logger, s, address)

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

        except (ConnectionError, TimeoutError) as e:
            self._logger.info(f'recv error, disconnect. {str(e)}')

        finally:
            self._socket.settimeout(None)


class TransClient(AudioTransmitter):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, chunk=None, **kwargs):
        super().__init__(logger, s, address)

        self._chunk = chunk if chunk else CHUNK
        self.stream = self.open_stream(input=True, frames_per_buffer=self._chunk, **kwargs)

    def run(self):
        try:
            while self.running:
                self._socket.sendto(self.stream.read(self._chunk), self._address)

            self._logger.info('Voice sender finished.')

        except ConnectionError:
            self._logger.info('Sendto error, disconnect.')


class UDPHandler(socketserver.BaseRequestHandler):
    logger = None

    def handle(self):
        command = self.request[0].strip().decode('utf-8')
        s = self.request[1]

        self.logger.info(f"From {self.client_address} recv: {command}.")
        cmds = command.split(' ')
        if len(cmds) != 5 or cmds[0] != 'AudioTransmitter' or cmds[1] != 'V1':
            self.logger.warning(f"Invalid command: {command}")
            return

        args = {'format': int(cmds[3].split('=')[1]),
                'channels': int(cmds[2].split('=')[1]),
                'rate': int(cmds[4].split('=')[1])}

        s.sendto('OK'.encode('utf-8'), self.client_address)

        self.logger.info(f"Service information: {args}.")
        with TransClient(self.logger, s, self.client_address, **args) as client, \
                TransServer(self.logger, s, self.client_address, **args) as server:
            server.start()
            client.start()

            server.join()

            client.finish()
            client.join()


def client_start(logger: logging.Logger, s: socket.socket, addr):
    logger.info(f"Connected {addr}.")
    s.sendto(f"AudioTransmitter V1 CHANNELS={CHANNELS} FORMAT={FORMAT} RATE={RATE}".encode('utf-8'), addr)
    response = s.recvfrom(1024)
    if response[0].decode('utf-8') != 'OK':
        logger.warning(f'Unknown response: {response}')
        return

    with TransServer(logger, s, addr) as server, TransClient(logger, s, addr) as client:
        server.start()
        client.start()

        input("Press enter key to exit.")

        client.finish()
        client.join()

        server.finish()
        server.join()


def get_parser():
    parser = argparse.ArgumentParser(description="Speed server for python. version: 0.1")
    parser.add_argument('--host', )
    parser.add_argument('--port', type=int, help='Socket port number')
    parser.add_argument('--log_file', help='Log file name')
    parser.add_argument('--log_level', help='Log level: debug, info, warning, error..')

    return parser.parse_args()


def main():
    args = get_parser()

    port = args.port if args.port else os.getenv('SPEED_TEST_PORT', DEFAULT_PORT)
    log_file = args.log_file if args.log_file else os.getenv('SPEED_LOG_FILE')
    log_level = args.log_level if args.log_level else os.getenv('SPEED_LOG_LEVEL', 'INFO')

    # create console handler and set level to debug
    if log_file:
        handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, delay=True)
        handler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s %(filename)s %(lineno)d: %(message)s'))
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s: %(message)s'))

    # add formatter to ch
    handler.setLevel(log_level)

    # create logger
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    logger.addHandler(handler)

    if args.host:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            client_start(logger, s, (args.host, port))

    else:
        logger.info('Begin UDP listen %d.' % port)

        UDPHandler.logger = logger
        with socketserver.UDPServer(('0.0.0.0', port), UDPHandler) as server:
            server.serve_forever()


if __name__ == '__main__':
    main()
