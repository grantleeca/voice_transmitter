import json
import logging
import socketserver
import sys
from logging.config import dictConfig

from tcp import TCPHandler, TCPClient
from udp import UDPHandler, UDPClient


def main():
    cfg_file = sys.argv[1] if len(sys.argv) > 1 else 'config.json'
    with open(f'config/{cfg_file}', 'rt') as fp:
        cfg = json.load(fp)

    dictConfig(cfg['logging'])
    logger = logging.getLogger('voice_transmitter')

    srv_info = cfg['server']
    port = srv_info['port']
    host = srv_info.get('host', '')

    if host == '':
        logger.info(f"Begin {srv_info['model']} listen %d." % port)

        if srv_info['model'] == 'TCP':
            TCPHandler.logger = logger
            with socketserver.TCPServer(('', port), TCPHandler) as server:
                server.serve_forever()
        else:
            UDPHandler.logger = logger
            with socketserver.UDPServer(('', port), UDPHandler) as server:
                server.serve_forever()
    else:
        if srv_info['model'] == 'TCP':
            with TCPClient(logger) as client:
                client.connect((host, port), **cfg['stream'])
        else:
            with UDPClient(logger, (host, port)) as client:
                client.connect(**cfg['stream'])


if __name__ == '__main__':
    main()
