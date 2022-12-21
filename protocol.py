import calendar
import hashlib
import socket
import struct
import time
import zlib

# import rsa

LOGIN_VERSION = 'AudioTransmitter 001'.encode('utf-8')
LOGIN_FORMAT = '!20siiiii'
LOGIN_LENGTH = struct.calcsize(LOGIN_FORMAT)

PROTOCOL_HEAD_FORMAT = '!cci'
PROTOCOL_FLAG = b'V'


class Protocol(object):
    token: str = 'password'
    last_login_time: int = 0

    @classmethod
    def set_token(cls, token):
        cls.token = token
        cls.last_login_time = 0

    @classmethod
    def hash_token(cls, nt: int):
        hash512 = hashlib.sha512()
        hash512.update(cls.token.encode('utf-8'))
        hash512.update(struct.pack('!i', nt))
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

        if cls.hash_token(response[5]) != data[LOGIN_LENGTH:]:
            return 'Token verify failed.'

        cls.last_login_time = response[5]
        return response[1:5]

    @classmethod
    def _pack_login(cls, format, channels, rate, chunk):
        now = calendar.timegm(time.gmtime())
        data = struct.pack(LOGIN_FORMAT, LOGIN_VERSION, format, channels, rate, chunk, now)
        return data + cls.hash_token(now)

    def __init__(self, s: socket.socket):
        self._socket = s

    def send(self, data):
        raise AssertionError('Protocol.send must be overloaded.')

    def recv(self, size):
        raise AssertionError('Protocol.recv must be overloaded.')

    def close(self):
        self._socket.close()

    def _read(self, size):
        res = b''
        while len(res) < size:
            buf = self.recv(size - len(res))
            res += buf

        return res

    def read(self):
        head = self._read(struct.calcsize(PROTOCOL_HEAD_FORMAT))
        flag, compress, size = struct.unpack(PROTOCOL_HEAD_FORMAT, head)
        if flag != PROTOCOL_FLAG:
            self.close()
            raise ConnectionError('Invalid protocol flag.')

        return self._read(size) if compress == b'N' else zlib.decompress(self._read(size))

    def write(self, data, compress=False):
        if compress:
            compress_data = zlib.compress(data)
            head = struct.pack(PROTOCOL_HEAD_FORMAT, PROTOCOL_FLAG, b'Y', len(compress_data))
            self.send(head + compress_data)
        else:
            head = struct.pack(PROTOCOL_HEAD_FORMAT, PROTOCOL_FLAG, b'N', len(data))
            self.send(head + data)

    def login(self, format, channels, rate, chunk):
        self.write(self._pack_login(format, channels, rate, chunk))

        self._socket.settimeout(None)

        return self.read().strip().decode('utf-8')

    def verify(self):
        data = self.read()
        request = self._verify_login(data)
        if isinstance(request, tuple):
            self.send_msg('OK')
            return request

        self.send_msg(request)

    def send_msg(self, msg: str):
        self.write(msg.encode('utf-8'))


class ProtocolTCP(Protocol):
    def send(self, data):
        self._socket.sendall(data)

    def recv(self, size):
        return self._socket.recv(size)


class ProtocolUDP(Protocol):
    def __init__(self, s: socket.socket, address):
        super().__init__(s)
        self._address = address

    def send(self, data):
        self._socket.sendto(data, self._address)

    def recv(self, size):
        while True:
            result = self._socket.recvfrom(size)
            if result[1] == self._address:
                return result[0]
