import logging
import threading

import pyaudio

from protocol import Protocol


class StreamThread(threading.Thread):
    pa = None

    @classmethod
    def open_stream(cls, **kwargs):
        if cls.pa is None:
            cls.pa = pyaudio.PyAudio()

        return cls.pa.open(**kwargs)

    @classmethod
    def terminate(cls):
        if cls.pa:
            cls.pa.terminate()
            cls.pa = None

    def __init__(self, logger: logging.Logger, p: Protocol, chunk=None):
        super().__init__()

        self.logger = logger
        self.stream = None
        self.remote = p
        self._chunk = chunk

    def run(self):
        if self._chunk is None:  # receiver
            stream_type = 'Receiver'
        else:
            stream_type = 'Sender'

        try:
            while True:
                if self._chunk is None:
                    self.stream.write(self.remote.read())

                else:
                    self.remote.write(self.stream.read(self._chunk, exception_on_overflow=False))

        except Exception as e:
            self.logger.debug(f'Voice {stream_type} disconnect. {type(e)}: {str(e)}')

        finally:
            self.stream.stop_stream()
            self.stream.close()
            self.remote.close()
            self.logger.info(f'Voice {stream_type} disconnect')
