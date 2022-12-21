import socket
import struct
import time
import zlib

# import rsa

LOGIN_FORMAT = '@20siiii'
LOGIN_VERSION = 'AudioTransmitter 001'.encode('utf-8')

PROTOCOL_HEAD_FORMAT = '@cci'
PROTOCOL_FLAG = b'V'

token: str = ''
last_login_time = time.gmtime()


class Protocol(object):
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
        self.write(struct.pack(LOGIN_FORMAT, LOGIN_VERSION, format, channels, rate, chunk))

        self._socket.settimeout(None)

        data = self.read()
        return True if data.strip().decode('utf-8') == 'OK' else False

    def verify(self):
        data = self.read()
        if len(data) != struct.calcsize(LOGIN_FORMAT):
            self.send_msg('Invalid.')
            return 'Invalid login format.'

        request = struct.unpack(LOGIN_FORMAT, data)
        if len(request) != 5:
            self.send_msg('Invalid.')
            return 'Invalid request parameter.'

        if request[0] != LOGIN_VERSION:
            self.send_msg('Invalid.')
            return 'Invalid request version.'

        self.send_msg('OK')
        return request[1:]

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
