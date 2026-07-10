# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""TLS echo server for proxy component benchmarks (PLAN.md).

Endpoints:
  POST /sink        -> reads request body, replies 16 bytes (request-direction sweep)
  GET  /bytes/<n>   -> replies with n bytes (response-direction sweep)
  GET  /ok          -> 16-byte reply (per-request constant sweep)

HTTP/1.1 keep-alive, threading server. Never logs request headers or bodies
(placeholder-rewritten credentials transit here on rung D).

Usage: python3 echo-server.py <port> <certfile> <keyfile>
"""

import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHUNK = b"x" * 65536


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # no per-request logging on the hot path
        pass

    def _reply(self, n: int):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(n))
        self.end_headers()
        left = n
        while left > 0:
            take = min(left, len(CHUNK))
            self.wfile.write(CHUNK[:take])
            left -= take

    def do_GET(self):
        if self.path.startswith("/bytes/"):
            try:
                n = int(self.path.split("/", 2)[2].split("?")[0])
            except (IndexError, ValueError):
                self.send_error(400)
                return
            self._reply(n)
        elif self.path.startswith("/ok"):
            self._reply(16)
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        left = length
        while left > 0:
            got = self.rfile.read(min(left, 65536))
            if not got:
                break
            left -= len(got)
        self._reply(16)


def main():
    port, cert, key = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print(f"echo server listening on :{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
