import logging
import threading
import time

import pyaudio

from protocol import Protocol


class StreamThread(threading.Thread):
    pa = None

    @classmethod
    def open_stream(cls, **kwargs):
        if cls.pa is None:
            cls.pa = pyaudio.PyAudio()

        return cls.pa.open(**kwargs)

    def __init__(self, logger: logging.Logger, p: Protocol, chunk=None):
        super().__init__()

        self.logger = logger
        self.stream = None
        self.socket = p
        self._chunk = chunk

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

    def run(self):
        if self._chunk is None:  # receiver
            stream_type = 'Receiver'
        else:
            stream_type = 'Sender'

        try:
            start_time = time.perf_counter()
            count = 0

            while True:
                if self._chunk is None:
                    data = self.socket.read()
                    self.stream.write(data)
                else:
                    data = self.stream.read(self._chunk)
                    self.socket.write(data, True)

                count += len(data)
                end_time = time.perf_counter()
                if end_time - start_time > 1.0:
                    self.logger.info(f"{stream_type} speed: {count / 1024 / (end_time - start_time): .2f} KB/s.")
                    start_time = end_time
                    count = 0

        except Exception as e:
            self.logger.debug(f'Voice {stream_type} disconnect. {type(e)}: {str(e)}')

        finally:
            self.socket.close()
            self.logger.info(f'Voice {stream_type} disconnect')
