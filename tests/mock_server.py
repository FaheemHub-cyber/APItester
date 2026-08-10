import http.server
import socketserver
import json
import os
import threading

PORT = 13845

class MockHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # suppress console logging

    def do_GET(self):
        # Serve the dynamic Amazon Lite test store
        if self.path == "/" or self.path == "/index.html" or self.path.startswith("/test-web-ui"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()

            # Look up path
            filepath = "test web ui/index.html"
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b"Amazon Lite Storefront file not found.")
            return

        # NTLM / Auth mock route
        elif self.path == "/ntlm-auth":
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

        # E-commerce products endpoint
        elif self.path == "/api/v1/products":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            products = [
                {"id": 101, "name": "Python Hacking Secrets", "price": 29.99},
                {"id": 102, "name": "Wireless Noise-Canceling Headphones", "price": 199.99},
                {"id": 103, "name": "Mechanical Keyboard (RGB)", "price": 89.99}
            ]
            self.wfile.write(json.dumps(products).encode("utf-8"))
            return

        # Legacy items route
        elif self.path == "/api/v2/items":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"items": [{"id": 1, "name": "TestItem"}]}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # E-commerce cart and checkout endpoints
        if self.path == "/api/v1/cart":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp_data = {"status": "success", "message": "Cart synchronized", "cart_size": len(body)}
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        elif self.path == "/api/v1/checkout":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp_data = {"status": "success", "order_id": "AL-83748293", "message": "Checkout completed"}
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        elif self.path == "/api/v2/items":
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
