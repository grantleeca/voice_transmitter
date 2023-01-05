import calendar
import hashlib
import logging
import socket
import struct
import time
import zlib

LOGIN_VERSION = 'AudioTransmitter 001'.encode('utf-8')
LOGIN_FORMAT = '!20s5i'
LOGIN_LENGTH = struct.calcsize(LOGIN_FORMAT)

PROTOCOL_HEAD_FORMAT = '!icc'
PROTOCOL_FLAG = b'V'
PROTOCOL_HEAD_LENGTH = struct.calcsize(PROTOCOL_HEAD_FORMAT)


class Protocol(object):
    passwd: str = 'password'
    compress: bool = True
    last_login_time: int = 0

    @classmethod
    def setup(cls, password, compress):
        cls.passwd = password
        cls.compress = compress
        cls.last_login_time = 0

    @classmethod
    def make_token(cls, num: int):
        hash512 = hashlib.sha512()
        hash512.update(cls.passwd.encode('utf-8'))
        hash512.update(struct.pack('!i', num))
        return hash512.digest()

    @classmethod
    def _verify_login(cls, data):
        if len(data) != LOGIN_LENGTH + 64:
            return 'Invalid login format.'

        response = struct.unpack(LOGIN_FORMAT, data[:LOGIN_LENGTH])
        if response[0] != LOGIN_VERSION:
            return 'Invalid request version.'

        if response[5] <= cls.last_login_time:
            return f'Invalid login time. {response[5]} <= {cls.last_login_time}'

        if cls.make_token(response[5]) != data[LOGIN_LENGTH:]:
            return 'Token verify failed.'

        cls.last_login_time = response[5]
        return response[1:5]

    @classmethod
    def _pack_login(cls, format, channels, rate, chunk):
        now = calendar.timegm(time.gmtime())
        data = struct.pack(LOGIN_FORMAT, LOGIN_VERSION, format, channels, rate, chunk, now)
        return data + cls.make_token(now)

    def __init__(self, logger: logging.Logger, s: socket.socket):
        self._logger = logger
        self._socket = s
        self._buffer = b''

    def send(self, data):
        raise AssertionError('Protocol.send must be overloaded.')

    def recv(self, size):
        raise AssertionError('Protocol.recv must be overloaded.')

    def close(self):
        self._socket.close()

    def _read(self, size):
        raise AssertionError('Protocol._read must be overloaded.')

    def read(self):
        head = self._read(PROTOCOL_HEAD_LENGTH)
        size, flag, compress = struct.unpack(PROTOCOL_HEAD_FORMAT, head)
        if flag != PROTOCOL_FLAG:
            self.close()
            raise ConnectionError('Invalid protocol flag.')

        size -= PROTOCOL_HEAD_LENGTH
        return self._read(size) if compress == b'N' else zlib.decompress(self._read(size))

    def write(self, data):
        if self.compress:
            compress_data = zlib.compress(data)
            head = struct.pack(PROTOCOL_HEAD_FORMAT, len(compress_data) + PROTOCOL_HEAD_LENGTH, PROTOCOL_FLAG, b'Y')
            self.send(head + compress_data)
        else:
            head = struct.pack(PROTOCOL_HEAD_FORMAT, len(data) + PROTOCOL_HEAD_LENGTH, PROTOCOL_FLAG, b'N')
            self.send(head + data)

    def login(self, format, channels, rate, chunk):
        self.write(self._pack_login(format, channels, rate, chunk))
        self._logger.debug('Send login request, wait reply.')
        return self.read().strip().decode('utf-8')

    def verify(self):
        request = self._verify_login(self.read())
        if isinstance(request, tuple):
            self.send_msg('OK')
            return request

        self.send_msg(request)

    def send_msg(self, msg: str):
        self.write(msg.encode('utf-8'))


class ProtocolTCP(Protocol):
    def send(self, data):
        self._socket.sendall(data)

    def _read(self, size):
        while len(self._buffer) < size:
            self._buffer += self._socket.recv(8192)

        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return result


class ProtocolUDP(Protocol):
    def __init__(self, logger: logging.Logger, s: socket.socket, address, data=None):
        super().__init__(logger, s)
        self._address = address
        self._buffer = data if data else b''

    def send(self, data):
        self._socket.sendto(data, self._address)

    def _read(self, size):
        while len(self._buffer) < size:
            response = self._socket.recvfrom(8192)
            if response[1] == self._address:
                self._buffer += response[0]

        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return result
