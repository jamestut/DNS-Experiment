#!/usr/bin/env python3

import socketserver
import argparse
import binascii
import json

from dnsfwd.log import log
from dnsfwd.engine import Engine
from dnsfwd import config

engine = None

class DNSUDPRequestHandler(socketserver.BaseRequestHandler):
	def handle(self):
		data = self.request[0]
		resp = engine.compute_response(data)
		if resp is not None:
			self.request[1].sendto(resp, self.client_address)

def main():
	global engine

	parser = argparse.ArgumentParser(description='A simple DNS forwarder app.')
	parser.add_argument('--single-thread', action='store_true',
		help='Run the DNS server in single threaded mode for debugging.')
	parser.add_argument('--config', required=True,
		help='Specify the configuration file.')
	args = parser.parse_args()

	# the server's data structure
	log(3, f"Loading configuration from: '{args.config}'.")
	with open(args.config, "rb") as f:
		ds = config.load_config(json.load(f))
	engine = Engine(ds)

	socksvr = socketserver.UDPServer if args.single_thread else socketserver.ThreadingUDPServer
	server = socksvr(('127.0.0.1', 53), DNSUDPRequestHandler)
	try:
		log(3, f"UDP server started.")
		server.serve_forever()
	except KeyboardInterrupt:
		pass
	finally:
		server.shutdown()

if __name__ == '__main__':
	main()
