import argparse
import http.server
import socketserver
import mimetypes
import os

class Handler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        base, ext = os.path.splitext(path)
        if ext == ".wasm":
            return "application/wasm"
        if ext == ".data":
            return "application/octet-stream"
        if ext == ".js":
            return "application/javascript"
        if ext == ".css":
            return "text/css"
        return mimetypes.guess_type(path)[0] or "application/octet-stream"

    def end_headers(self):
        # utile per evitare cache strana durante i test
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Directory che contiene index.html")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    os.chdir(args.dir)
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
        print(f"Serving on http://localhost:{args.port}/index.html from {os.getcwd()}")
        httpd.serve_forever()

if __name__ == "__main__":
    main()
