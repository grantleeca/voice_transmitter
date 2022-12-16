import logging
import threading

import pyaudio

HEAD_FORMAT = '@20siiii'
HEAD_VERSION = 'AudioTransmitter 001'.encode('utf-8')

# CHUNK = 1024  # 每个缓冲区的帧数


class StreamThread(threading.Thread):
    pa = None

    @classmethod
    def open_stream(cls, **kwargs):
        if cls.pa is None:
            cls.pa = pyaudio.PyAudio()

        return cls.pa.open(**kwargs)

    def __init__(self, logger: logging.Logger):
        super().__init__()

        self._logger = logger

        # self.running = True
        self.stream = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

    # def finish(self):
    #     self.running = False
