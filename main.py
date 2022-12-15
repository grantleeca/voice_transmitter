import argparse
import logging
import os
import socket
import socketserver
import sys
import threading
import wave
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler

import pyaudio

DEFAULT_PORT = 1029

CHUNK = 1024  # 每个缓冲区的帧数
FORMAT = pyaudio.paInt16  # 采样位数
CHANNELS = 1  # 单声道
RATE = 44100  # 采样频率

pa = pyaudio.PyAudio()


@contextmanager
def open_audio_stream(*args, **kwargs):
    # instantiate PyAudio (1)

    # open stream (2)
    stream = pa.open(*args, **kwargs)

    # play stream (3)
    yield stream

    # stop stream (4)
    stream.stop_stream()
    stream.close()

    # close PyAudio (5)
    # p.terminate()


def record_audio(wave_out_path, record_second):
    """ 录音功能 """
    with open_audio_stream(format=FORMAT,
                           channels=CHANNELS,
                           rate=RATE,
                           input=True,
                           frames_per_buffer=CHUNK) as stream:
        wf = wave.open(wave_out_path, 'wb')  # 打开 wav 文件。
        wf.setnchannels(CHANNELS)  # 声道设置
        wf.setsampwidth(pyaudio.get_sample_size(FORMAT))  # 采样位数设置
        wf.setframerate(RATE)  # 采样频率设置

        for _ in range(0, int(RATE * record_second / CHUNK)):
            data = stream.read(CHUNK)
            wf.writeframes(data)  # 写入数据

        wf.close()

    pa.terminate()


def play_audio(wave_file):
    with wave.open(wave_file, 'rb') as wf:
        with open_audio_stream(format=pyaudio.get_format_from_width(wf.getsampwidth()),
                               channels=wf.getnchannels(),
                               rate=wf.getframerate(),
                               output=True) as stream:
            # read data
            data = wf.readframes(CHUNK)

            while len(data):
                stream.write(data)
                data = wf.readframes(CHUNK)

    pa.terminate()


class AudioTransmitter(threading.Thread):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, sample_size, channels, rate, chunk):
        super().__init__()

        self.running = True
        self._logger = logger
        self._socket = s
        self._client_address = address
        self._size = sample_size
        self._channels = channels
        self._rate = rate
        self._chunk = chunk

    def send_data(self, data):
        try:
            self._socket.sendto(data, self._client_address)
            return True

        except ConnectionError:
            self._logger.info('Sendto error, disconnect.')
            return False

    def recv_data(self, buf_size):
        try:
            self._socket.settimeout(3.0)
            response = self._socket.recvfrom(buf_size)
            self._client_address = response[1]
            return response[0]

        except (ConnectionError, TimeoutError) as e:
            self._logger.info(f'recv error, disconnect. {str(e)}')
            self.running = False
            return None

    def run(self):
        self.running = True
        self.receiver()

    def receiver(self):
        self._logger.debug(f'Begin receiver. format:{self._size}, channels:{self._channels}, rate:{self._rate}')

        with open_audio_stream(format=self._size, channels=self._channels, rate=self._rate, output=True) as stream:
            self._logger.debug('Opened output audio stream.')
            while self.running:
                data = self.recv_data(8192)
                if data is None:
                    break

                stream.write(data)

        self._logger.info('Voice receiver finished.')

    def sender(self):
        self._logger.debug(
            f'Begin sender. format:{self._size}, channels:{self._channels}, rate:{self._rate}, chunk:{self._chunk}')

        with open_audio_stream(format=self._size, channels=self._channels, rate=self._rate, input=True,
                               frames_per_buffer=self._chunk) as stream:
            self._logger.debug('Opened input audio stream.')

            while self.running:
                data = stream.read(self._chunk)
                if not self.send_data(data):
                    break

        self._logger.info('Voice sender finished.')


class UDPHandler(socketserver.BaseRequestHandler):
    logger = None

    def handle(self):
        command = self.request[0].strip().decode('utf-8')
        s = self.request[1]

        self.logger.info(f"From {self.client_address} recv: {command}.")
        cmds = command.split(' ')
        if len(cmds) != 5 or cmds[0] != 'AudioTransmitter' or cmds[1] != 'V1':
            self.logger.warning(f"Invalid command: {command}")
            return command

        channels = int(cmds[2].split('=')[1])
        sample_size = int(cmds[3].split('=')[1])
        rate = int(cmds[4].split('=')[1])

        s.sendto('OK'.encode('utf-8'), self.client_address)

        self.logger.info(f'Service information: sample_size: {sample_size}, channels: {channels}, rate: {rate}.')
        server = AudioTransmitter(self.logger, s, self.client_address, sample_size, channels, rate, CHUNK)
        server.start()
        server.sender()


class UDPClient:
    def __init__(self, logger: logging.Logger):
        self._logger = logger
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._server_addr = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._socket.close()
        self._socket = None

    def connect(self, addr):
        # self._logger.debug(f"Begin connect to {addr}")
        # self._conn.connect(addr)
        self._server_addr = addr
        self._logger.info(f"Connected {addr}.")

    def send_msg(self, msg: str):
        self._socket.sendto(msg.encode('utf-8'), self._server_addr)
        response = self._socket.recvfrom(4096)
        self._server_addr = response[1]
        return response[0].decode('utf-8')

    def start(self, addr):
        self.connect(addr)
        response = self.send_msg(f"AudioTransmitter V1 CHANNELS={CHANNELS} FORMAT={FORMAT} RATE={RATE}")
        if response == 'OK':
            at = AudioTransmitter(self._logger, self._socket, self._server_addr, FORMAT, CHANNELS, RATE, CHUNK)
            at.start()
            self._logger.info('Receiver thread started. begin sender ...')
            at.sender()
        else:
            self._logger.warning(f'Unknown response: {response}')


def get_parser():
    parser = argparse.ArgumentParser(description="Speed server for python. version: 0.1")
    # parser.add_argument('--model', choices=['TCP', 'UDP'], default='TCP', help='Set server model.')
    parser.add_argument('--server', '-s', action="store_true")
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

    if args.server:
        logger.info('Begin TCP listen %d.' % port)

        UDPHandler.logger = logger
        with socketserver.UDPServer(('0.0.0.0', port), UDPHandler) as server:
            server.serve_forever()

    else:
        if args.host:
            with UDPClient(logger) as client:
                client.start((args.host, port))
        else:
            logger.warning('In client mode, the name or IP address of the server to bo connected must entered.')


# repeat_q = queue.Queue()
# instantiate PyAudio (1)
# pa = pyaudio.PyAudio()


# def repeat_play():
#     print("Worker start.")
#     with open_audio_stream(pa, format=FORMAT, channels=CHANNELS, rate=RATE, output=True) as stream:
#         while True:
#             data = repeat_q.get()
#             stream.write(data)
#             repeat_q.task_done()


# def Repeater(record_second):
#     print("start work thread.")
#     threading.Thread(target=repeat_play, daemon=True).start()
#
#     print("open input audio stream.")
#     with open_audio_stream(pa, format=FORMAT,
#                            channels=CHANNELS,
#                            rate=RATE,
#                            input=True,
#                            frames_per_buffer=CHUNK) as stream:
#
#         for _ in range(0, int(RATE * record_second / CHUNK)):
#             data = stream.read(CHUNK)
#             repeat_q.put(data)
#
#     repeat_q.join()
#     print('Finished')


if __name__ == '__main__':
    # record_audio('test.wav', 10)
    main()
    # Repeater(3)
