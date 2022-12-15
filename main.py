import argparse
import logging
import os
import socketserver
import sys
from logging.handlers import RotatingFileHandler

from tcp import TCPHandler, TCPClient
from udp import UDPHandler, UDPClient

DEFAULT_PORT = 1029


def get_parser():
    parser = argparse.ArgumentParser(description="Speed server for python. version: 0.1")
    parser.add_argument('--model', choices=['TCP', 'UDP'], default='TCP', help='connect mode.')
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
        log_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, delay=True)
        log_handler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s %(filename)s %(lineno)d: %(message)s'))
    else:
        log_handler = logging.StreamHandler(sys.stdout)
        log_handler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s: %(message)s'))

    # add formatter to ch
    log_handler.setLevel(log_level)

    # create logger
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    logger.addHandler(log_handler)

    if args.host:
        if args.model == 'TCP':
            with TCPClient(logger) as client:
                client.connect((args.host, port))
        else:
            with UDPClient(logger) as client:
                client.connect((args.host, port))

    else:
        handle = TCPHandler if args.model == 'TCP' else UDPHandler

        logger.info(f'Begin {args.model} listen %d.' % port)

        handle.logger = logger
        with socketserver.UDPServer(('0.0.0.0', port), handle) as server:
            server.serve_forever()


if __name__ == '__main__':
    main()
