import argparse
import json
import logging
import socketserver
from logging.config import dictConfig

from protocol import Protocol
from stream_thread import StreamThread
from tcp import TCPHandler, TCPClient
from udp import UDPHandler, UDPClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c', default='config.json', help='config file name.')
    parser.add_argument('--server', action='store_true', help='Voice transmitter model.')

    args = parser.parse_args()

    with open(args.config, 'rt') as fp:
        cfg = json.load(fp)

    dictConfig(cfg['logging'])
    logger = logging.getLogger('voice_transmitter')

    try:
        if args.server:
            srv_info = cfg['server']
            port = srv_info.get('port', 1029)
            Protocol.setup(srv_info['token'], srv_info.get('compress', False))

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
            client_info = cfg['client']
            host = client_info['host']
            port = client_info.get('port', 1029)

            Protocol.setup(client_info['token'], client_info.get('compress', False))

            if client_info['model'] == 'TCP':
                with TCPClient(logger) as client:
                    client.connect((host, port), **cfg['stream'])
            else:
                with UDPClient(logger, (host, port)) as client:
                    client.connect(**cfg['stream'])

    except Exception as e:
        logger.exception(f"Program except exit: {e}.")

    finally:
        StreamThread.terminate()


if __name__ == '__main__':
    main()
