"""Local helper: serves art/ and saves PNGs rendered by render.html (POST /save?name=file.png)."""
import http.server
import os
import re
import sys
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def do_POST(self):
        name = parse_qs(urlparse(self.path).query).get("name", [""])[0]
        if not re.fullmatch(r"[\w.-]+\.png", name):
            self.send_error(400, "bad name")
            return
        data = self.rfile.read(int(self.headers["Content-Length"]))
        with open(os.path.join(HERE, name), "wb") as fh:
            fh.write(data)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"saved %d bytes" % len(data))


http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8766), Handler).serve_forever()
