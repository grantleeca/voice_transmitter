import logging
from threading import Thread

import pyaudio

from protocol import Protocol


class InputThread(Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True

    def run(self) -> None:
        input('Press enter key to exit.')


class StreamThread(Thread):
    pa = None
    stop = False

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
            while not self.stop:
                if self._chunk is None:
                    self.stream.write(self.remote.read())

                else:
                    self.remote.write(self.stream.read(self._chunk, exception_on_overflow=False))

        except Exception as e:
            self.logger.exception(f'{stream_type} exception. {type(e)}: {str(e)}')

        finally:
            self.stream.stop_stream()
            self.stream.close()
            self.remote.close()
            self.logger.info(f'Voice {stream_type} disconnect')
