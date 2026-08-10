import http.server
import socketserver
import json
import threading

PORT = 13845

class MockHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # suppress console logging

    def do_GET(self):
        # 1. NTLM / Auth mock route
        if self.path == "/ntlm-auth":
            auth_header = self.headers.get("Authorization", "")
            if not auth_header:
                self.send_response(401)
                self.send_header("WWW-Authenticate", "NTLM")
                self.send_header("WWW-Authenticate", "Basic realm=\"Mock\"")
                self.end_headers()
                self.wfile.write(b"Unauthorized - Auth required")
                return

            if auth_header.startswith("Basic ") or auth_header.startswith("NTLM "):
                # Fast track authentication for the test suite
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "authenticated", "auth": "ntlm"}).encode("utf-8"))
                return

            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Bad Request")
            return

        # 2. HTML Rendering mock route
        elif self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """<!DOCTYPE html>
<html>
<head>
    <title>WebInvader Mock Server</title>
    <style>body { font-family: sans-serif; background-color: #f0f2f5; margin: 40px; }</style>
</head>
<body>
    <h1>Welcome to WebInvader Test Application</h1>
    <p>This is a sample HTML response rendered by WebInvader browser viewer.</p>
    <div style="padding: 15px; background-color: #fff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <h3>Interactive Form</h3>
        <form action="/api/v2/items" method="POST">
            <label>Name: <input type="text" name="name" value="TestItem"/></label>
            <input type="submit" value="Submit Form"/>
        </form>
    </div>
</body>
</html>"""
            self.wfile.write(html.encode("utf-8"))
            return

        # 3. Simple JSON item endpoint
        elif self.path == "/api/v2/items":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"items": [{"id": 1, "name": "TestItem"}]}).encode("utf-8"))
            return

        # 4. Exclude filter pattern check
        elif self.path == "/other-endpoint":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Other Endpoint Content")
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_POST(self):
        if self.path == "/api/v2/items":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b""

            # Echo input in response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp_data = {
                "status": "success",
                "received_body": body.decode("utf-8", errors="ignore"),
                "headers": dict(self.headers)
            }
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")


class ThreadedMockServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


_server_instance = None
_server_thread = None

def start_server():
    global _server_instance, _server_thread
    if _server_instance is None:
        _server_instance = ThreadedMockServer(("127.0.0.1", PORT), MockHTTPRequestHandler)
        _server_thread = threading.Thread(target=_server_instance.serve_forever, daemon=True)
        _server_thread.start()
        print(f"Mock server started on http://127.0.0.1:{PORT}")

def stop_server():
    global _server_instance
    if _server_instance is not None:
        _server_instance.shutdown()
        _server_instance.server_close()
        _server_instance = None
        print("Mock server stopped.")

if __name__ == "__main__":
    start_server()
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_server()
