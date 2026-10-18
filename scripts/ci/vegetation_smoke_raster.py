"""Controlled Raster readiness dependency, isolated inside the CI Docker network."""

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/readyz":
            self.send_error(404)
            return
        ready = not Path("/tmp/raster-unready").exists()
        self.send_response(200 if ready else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ready":true}' if ready else b'{"ready":false}')


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8001), Handler).serve_forever()
