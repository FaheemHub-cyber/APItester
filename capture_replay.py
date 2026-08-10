import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import json
import csv
import queue
import urllib.parse
import sys
import os
import socket
import select
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver
import requests
from requests.auth import HTTPBasicAuth

# Safe import for requests_ntlm
try:
    from requests_ntlm import HttpNtlmAuth
    HAS_NTLM = True
except ImportError:
    HttpNtlmAuth = None
    HAS_NTLM = False

# Safe import for tkinterweb HTML rendering
try:
    from tkinterweb import HtmlFrame
    HAS_TKINTERWEB = True
except ImportError:
    HAS_TKINTERWEB = False


# Theme Palette & Style Configurations
class Theme:
    BG_MAIN = "#f8f9fa"
    BG_CARD = "#ffffff"
    FG_MAIN = "#212529"
    FG_MUTED = "#6c757d"
    ACCENT_COLOR = "#0d6efd"  # Modern Light Blue
    ACCENT_HOVER = "#0b5ed7"
    BORDER_COLOR = "#dee2e6"

    # Status Row Colors
    COLOR_SUCCESS = "#198754"  # Modern Green
    COLOR_REDIRECT = "#fd7e14" # Modern Orange
    COLOR_ERROR = "#dc3545"    # Modern Red

    FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "Helvetica"

    @classmethod
    def apply(cls, root):
        style = ttk.Style()
        style.theme_use("clam")

        # Base styles
        style.configure(".", font=(cls.FONT_FAMILY, 10), background=cls.BG_MAIN, foreground=cls.FG_MAIN)
        style.configure("TFrame", background=cls.BG_MAIN)
        style.configure("Card.TFrame", background=cls.BG_CARD, borderwidth=1, relief="solid")

        # Tabs / Notebook
        style.configure("TNotebook", background=cls.BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", font=(cls.FONT_FAMILY, 10, "bold"), background=cls.BORDER_COLOR, padding=[12, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", cls.BG_CARD), ("active", cls.BG_MAIN)],
                  foreground=[("selected", cls.ACCENT_COLOR)])

        # Tables / Treeview
        style.configure("Treeview", font=(cls.FONT_FAMILY, 10), rowheight=26, background=cls.BG_CARD, fieldbackground=cls.BG_CARD, borderwidth=0)
        style.configure("Treeview.Heading", font=(cls.FONT_FAMILY, 10, "bold"), background=cls.BORDER_COLOR, foreground=cls.FG_MAIN, relief="flat")
        style.map("Treeview", background=[("selected", cls.ACCENT_COLOR)], foreground=[("selected", "#ffffff")])

        # Flat Buttons with consistent sizing
        style.configure("TButton", font=(cls.FONT_FAMILY, 10, "bold"), background=cls.BORDER_COLOR, borderwidth=0, padding=[12, 6])
        style.map("TButton",
                  background=[("active", cls.ACCENT_COLOR), ("selected", cls.ACCENT_COLOR)],
                  foreground=[("active", "#ffffff"), ("selected", "#ffffff")])

        style.configure("Accent.TButton", font=(cls.FONT_FAMILY, 10, "bold"), background=cls.ACCENT_COLOR, foreground="#ffffff", borderwidth=0, padding=[12, 6])
        style.map("Accent.TButton", background=[("active", cls.ACCENT_HOVER)])

        # Labels
        style.configure("TLabel", font=(cls.FONT_FAMILY, 10), background=cls.BG_MAIN, foreground=cls.FG_MAIN)
        style.configure("Title.TLabel", font=(cls.FONT_FAMILY, 14, "bold"), foreground=cls.ACCENT_COLOR)
        style.configure("Section.TLabel", font=(cls.FONT_FAMILY, 11, "bold"), foreground=cls.FG_MAIN)

        # Entries & Comboboxes
        style.configure("TEntry", font=(cls.FONT_FAMILY, 10), padding=5)
        style.configure("TCombobox", font=(cls.FONT_FAMILY, 10), padding=5)


# Local Configuration storage manager (config.json)
class ConfigManager:
    FILENAME = "config.json"

    @classmethod
    def load(cls):
        if os.path.exists(cls.FILENAME):
            try:
                with open(cls.FILENAME, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "targets": [{"host": "http://localhost:13845", "pattern": "*"}],
            "auth_type": "No Auth",
            "username": "",
            "password": "",
            "token": ""
        }

    @classmethod
    def save(cls, data):
        try:
            with open(cls.FILENAME, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


# Filters URLs on Target Host & Matching Pattern across ALL active target definitions
def matches_filter(url, targets):
    if not url or not targets:
        return False

    for target in targets:
        host = target.get("host", "").strip()
        pattern = target.get("pattern", "").strip()

        if not host or not pattern:
            continue

        parsed_target = urllib.parse.urlparse(host)
        parsed_url = urllib.parse.urlparse(url)

        # 1. Domain/Host verification
        host_match = False
        if parsed_target.netloc:
            if parsed_target.netloc.lower() in parsed_url.netloc.lower() or host.lower() in url.lower():
                host_match = True
        else:
            if host.lower() in url.lower():
                host_match = True

        if not host_match:
            continue

        # 2. Pattern verification (Wildcard * captures all requests)
        if pattern == "*":
            return True
        if pattern.lower() in url.lower():
            return True

    return False


# Returns UI Tag Class for HTTP status code colors
def classify_status(status_code):
    try:
        sc = int(status_code)
        if 200 <= sc < 300:
            return "success"
        elif 300 <= sc < 400:
            return "redirect"
        return "error"
    except Exception:
        return "neutral"


# Renders raw response preview nicely fallback visual view
class TKHTMLRenderer:
    @classmethod
    def render(cls, parent, html_content, target_name):
        if HAS_TKINTERWEB:
            try:
                frame = HtmlFrame(parent)
                frame.pack(fill="both", expand=True)
                if isinstance(html_content, bytes):
                    html_content = html_content.decode("utf-8", errors="ignore")
                frame.load_html(html_content)
                return frame, "html"
            except Exception:
                pass

        # Simple Text Fallback Rendering
        fb_frame = ttk.Frame(parent)
        fb_frame.pack(fill="both", expand=True)
        lbl_info = ttk.Label(fb_frame, text="[Rendering Fallback - Simple Raw Preview]", foreground=Theme.FG_MUTED)
        lbl_info.pack(anchor="nw", pady=2)

        txt = tk.Text(fb_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        txt.pack(fill="both", expand=True)
        if isinstance(html_content, bytes):
            html_content = html_content.decode("utf-8", errors="ignore")
        txt.insert("1.0", html_content)
        return txt, "text"


# Calculates deduplication fingerprint hash to skip identical requests
def make_record_hash(url, method, req_body, status_code):
    body_str = req_body
    if isinstance(body_str, bytes):
        body_str = body_str.decode("utf-8", errors="ignore")
    raw = f"{url}|{method}|{body_str}|{status_code}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


# Assembles HTTP trace fields into a standard dictionary
def build_traffic_record(record_id, method, url, req_headers, req_body, status_code, resp_headers, resp_body):
    return {
        "id": record_id,
        "method": method,
        "url": url,
        "request_headers": req_headers,
        "request_body": req_body,
        "status_code": status_code,
        "response_headers": resp_headers,
        "response_body": resp_body
    }


# Custom Threaded HTTP Proxy Server
class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def handle_request(self):
        method = self.command
        url = self.path

        # Standardize full proxy URL if path is relative
        if not url.startswith("http://") and not url.startswith("https://"):
            host = self.headers.get("Host", "")
            url = f"http://{host}{url}"

        # Parse headers
        headers = {}
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length"):
                headers[k] = v

        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        try:
            # Forward the call synchronously using requests
            # Disable proxies for outgoing requests to prevent infinite routing loop!
            resp = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=body,
                allow_redirects=False,
                timeout=15,
                proxies={"http": None, "https": None}
            )

            # Send response headers back to client
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp.content)))
            self.end_headers()

            # Write response content back to client
            self.wfile.write(resp.content)

            # Check domain and pattern constraints and record
            self.server.app.check_and_capture(
                method=method,
                url=url,
                req_headers=dict(self.headers),
                req_body=body,
                status_code=resp.status_code,
                resp_headers=dict(resp.headers),
                resp_body=resp.content
            )

        except Exception as e:
            err_msg = f"Proxy forwarding error: {str(e)}".encode('utf-8')
            try:
                self.send_response(502)
                self.send_header("Content-Length", str(len(err_msg)))
                self.end_headers()
                self.wfile.write(err_msg)
            except Exception:
                pass

    def do_CONNECT(self):
        # Handle HTTPS CONNECT tunneling gracefully (no inspection)
        try:
            host, port = self.path.split(":")
            port = int(port)
        except ValueError:
            self.send_error(400, "Bad CONNECT request")
            return

        try:
            sock = socket.create_connection((host, port), timeout=10)
        except Exception:
            self.send_error(502, "Gateway error")
            return

        try:
            self.send_response(200, "Connection Established")
            self.end_headers()
        except Exception:
            return

        # Tunnel data through select
        self.wfile.flush()
        conns = [self.connection, sock]
        keep_going = True
        while keep_going:
            r, _, _ = select.select(conns, [], [], 10)
            if not r:
                break
            for s in r:
                other = sock if s is self.connection else self.connection
                try:
                    data = s.recv(8192)
                    if not data:
                        keep_going = False
                        break
                    other.sendall(data)
                except Exception:
                    keep_going = False
                    break

    # Proxy routes
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def do_PUT(self): self.handle_request()
    def do_DELETE(self): self.handle_request()
    def do_PATCH(self): self.handle_request()
    def do_OPTIONS(self): self.handle_request()
    def do_HEAD(self): self.handle_request()


# Playwright CDP Interception thread loop
class CDPClient:
    def __init__(self, app):
        self.app = app
        self.running = False

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def run(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()

                def handle_response(response):
                    try:
                        req = response.request
                        url = response.url
                        method = req.method
                        req_headers = req.headers
                        req_body = req.post_data or ""

                        status = response.status
                        resp_headers = response.headers

                        try:
                            resp_body = response.body()
                        except Exception:
                            resp_body = b""

                        self.app.check_and_capture(
                            method=method,
                            url=url,
                            req_headers=req_headers,
                            req_body=req_body,
                            status_code=status,
                            resp_headers=resp_headers,
                            resp_body=resp_body
                        )
                    except Exception as e:
                        print(f"CDP callback handler exception: {e}")

                page.on("response", handle_response)

                # Navigate to the first active target host URL if available
                targets = self.app.active_targets
                target_host = targets[0]["host"] if targets else ""
                if target_host:
                    try:
                        page.goto(target_host)
                    except Exception:
                        pass

                while self.running:
                    try:
                        page.wait_for_timeout(100)
                    except Exception:
                        break
                browser.close()
        except ImportError:
            self.app.after(0, lambda: messagebox.showerror("Playwright Error", "Playwright is not initialized properly. Install with:\npip install playwright && playwright install"))
        except Exception as e:
            print(f"CDP Client Thread Exception: {e}")
        finally:
            self.running = False
            self.app.after(0, lambda: self.app.btn_capture.config(text="🌐 CAPTURE", style="Accent.TButton"))


# Built-in thread-safe Proxy interceptor server on Port 8888
class InbuiltProxyServer:
    def __init__(self, app):
        self.app = app
        self.server = None
        self.running = False

    def start(self):
        try:
            self.server = ThreadedHTTPServer(("127.0.0.1", 8888), ProxyHandler)
            self.server.app = self.app
            self.running = True
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            messagebox.showinfo("Proxy Active", "Local HTTP Proxy Server started on port 8888.\nConfigure your browser or application proxy to redirect traffic.")
        except Exception as e:
            self.running = False
            messagebox.showerror("Proxy Error", f"Failed to start proxy server on port 8888:\n{str(e)}")

    def stop(self):
        if self.running and self.server:
            self.server.shutdown()
            self.server.server_close()
        self.running = False


# Replay Engine that handles NTLM/Basic/Bearer Auth Replays
class ReplayEngine:
    @classmethod
    def execute(cls, method, url, headers, body, auth_type, username="", password="", token=""):
        req_headers = cls.parse_headers(headers)

        auth_obj = None
        if auth_type == "Basic Auth":
            auth_obj = HTTPBasicAuth(username, password)
        elif auth_type == "NTLM":
            if not HAS_NTLM:
                raise ImportError("requests-ntlm is not installed. Install with: pip install requests-ntlm")
            auth_obj = HttpNtlmAuth(username, password)
        elif auth_type == "Bearer Token":
            req_headers["Authorization"] = f"Bearer {token}"

        if isinstance(body, str):
            body = body.encode("utf-8")

        resp = requests.request(
            method=method,
            url=url,
            headers=req_headers,
            data=body,
            auth=auth_obj,
            allow_redirects=False,
            timeout=15
        )
        return resp

    @classmethod
    def parse_headers(cls, headers):
        # Parses newline-separated headers format (e.g. Host: localhost:13845)
        # Skips rows starting with "//"
        req_headers = {}
        if isinstance(headers, dict):
            return headers

        if isinstance(headers, str):
            # Check if it looks like JSON
            trimmed = headers.strip()
            if trimmed.startswith("{") and trimmed.endswith("}"):
                try:
                    return json.loads(trimmed)
                except Exception:
                    pass

            # Parsing custom Newline/Colon Format with '//' comment capability
            for line in headers.split("\n"):
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                if ":" in line:
                    k, v = line.split(":", 1)
                    req_headers[k.strip()] = v.strip()
        return req_headers

    @classmethod
    def format_headers(cls, headers_dict):
        # Formats dict headers to clean newline-separated text rows
        if not headers_dict:
            return ""
        if isinstance(headers_dict, str):
            try:
                headers_dict = json.loads(headers_dict)
            except Exception:
                return headers_dict

        lines = []
        for k, v in headers_dict.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)


# API Requester Frame (Postman Lite Custom Sender Interface)
class InbuiltBrowserFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.create_widgets()

    def create_widgets(self):
        # Method, URL and Send Request
        r1 = ttk.Frame(self)
        r1.pack(fill="x", pady=2)

        ttk.Label(r1, text="Method:").pack(side="left", padx=2)
        self.method_var = tk.StringVar(value="GET")
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
        self.method_cb = ttk.Combobox(r1, textvariable=self.method_var, values=methods, state="readonly", width=10, font=(Theme.FONT_FAMILY, 10))
        self.method_cb.pack(side="left", padx=5)

        ttk.Label(r1, text="URL:").pack(side="left", padx=10)
        self.url_entry = ttk.Entry(r1, font=(Theme.FONT_FAMILY, 10))
        self.url_entry.insert(0, "http://localhost:13845/")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_send = ttk.Button(r1, text="🚀 SEND REQUEST", style="Accent.TButton", command=self.send_request)
        self.btn_send.pack(side="right", padx=5)

        # Authentication Selection
        r2 = ttk.Frame(self)
        r2.pack(fill="x", pady=5)

        ttk.Label(r2, text="Auth Type:").pack(side="left", padx=2)
        self.auth_var = tk.StringVar(value="None")
        auths = ["None", "NTLM", "Basic Auth", "Bearer Token"]
        self.auth_cb = ttk.Combobox(r2, textvariable=self.auth_var, values=auths, state="readonly", width=12, font=(Theme.FONT_FAMILY, 10))
        self.auth_cb.pack(side="left", padx=5)
        self.auth_cb.bind("<<ComboboxSelected>>", self.on_auth_change)

        self.auth_inputs = ttk.Frame(r2)
        self.auth_inputs.pack(side="left", fill="x", padx=10)

        self.lbl_u = ttk.Label(self.auth_inputs, text="User:")
        self.ent_u = ttk.Entry(self.auth_inputs, width=15, font=(Theme.FONT_FAMILY, 10))
        self.lbl_p = ttk.Label(self.auth_inputs, text="Pass:")
        self.ent_p = ttk.Entry(self.auth_inputs, show="*", width=15, font=(Theme.FONT_FAMILY, 10))
        self.lbl_t = ttk.Label(self.auth_inputs, text="Token:")
        self.ent_t = ttk.Entry(self.auth_inputs, width=25, font=(Theme.FONT_FAMILY, 10))
        self.update_auth_inputs_visibility()

        # Body and Headers editor
        r3 = ttk.Frame(self)
        r3.pack(fill="both", expand=True, pady=5)

        lf_h = ttk.LabelFrame(r3, text="Request Headers (NewLine & Colon separate; prepend // to disable)", padding=5)
        lf_h.pack(side="left", fill="both", expand=True, padx=2)
        self.headers_text = tk.Text(lf_h, wrap="word", height=6, background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        self.headers_text.insert("1.0", "Content-Type: application/json\n//Authorization: Bearer my-token-example")
        self.headers_text.pack(fill="both", expand=True)

        lf_b = ttk.LabelFrame(r3, text="Request Body / POST Payload", padding=5)
        lf_b.pack(side="right", fill="both", expand=True, padx=2)
        self.body_text = tk.Text(lf_b, wrap="word", height=6, background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        self.body_text.pack(fill="both", expand=True)

        # Sub-Notebook details
        self.details = ttk.Notebook(self)
        self.details.pack(fill="both", expand=True, pady=5)

        self.req_sent_frame = ttk.Frame(self.details, padding=5)
        self.details.add(self.req_sent_frame, text="📄 Sent Request")
        self.req_sent_text = tk.Text(self.req_sent_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        self.req_sent_text.pack(fill="both", expand=True)

        self.resp_recv_frame = ttk.Frame(self.details, padding=5)
        self.details.add(self.resp_recv_frame, text="📄 Received Response")
        self.resp_recv_text = tk.Text(self.resp_recv_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        self.resp_recv_text.pack(fill="both", expand=True)

        self.visual_frame = ttk.Frame(self.details, padding=5)
        self.details.add(self.visual_frame, text="🎨 Render Visual")
        self.render_container = ttk.Frame(self.visual_frame)
        self.render_container.pack(fill="both", expand=True)

    def populate_custom_sender_fields(self, item):
        # Populate URL & Method
        self.method_var.set(item.get("method", "GET"))
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, item.get("url", ""))

        # Populate Headers (Formatted cleanly)
        headers = item.get("request_headers", {})
        self.headers_text.delete("1.0", tk.END)
        self.headers_text.insert("1.0", ReplayEngine.format_headers(headers))

        # Populate Body
        body = item.get("request_body", "")
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="ignore")
        self.body_text.delete("1.0", tk.END)
        self.body_text.insert("1.0", body)

        # Switch notebook to custom sender tab (which is tab index 2)
        self.app.notebook.select(self.app.inbuilt_browser)
        messagebox.showinfo("Custom Sender", "Request details transferred to Custom Sender successfully.")

    def on_auth_change(self, event=None):
        self.update_auth_inputs_visibility()

    def update_auth_inputs_visibility(self):
        self.lbl_u.pack_forget()
        self.ent_u.pack_forget()
        self.lbl_p.pack_forget()
        self.ent_p.pack_forget()
        self.lbl_t.pack_forget()
        self.ent_t.pack_forget()

        auth_type = self.auth_var.get()
        if auth_type == "Basic Auth" or auth_type == "NTLM":
            self.lbl_u.pack(side="left", padx=2)
            self.ent_u.pack(side="left", padx=5)
            self.lbl_p.pack(side="left", padx=2)
            self.ent_p.pack(side="left", padx=5)
        elif auth_type == "Bearer Token":
            self.lbl_t.pack(side="left", padx=2)
            self.ent_t.pack(side="left", padx=5)

    def send_request(self):
        method = self.method_var.get()
        url = self.url_entry.get().strip()
        auth_type = self.auth_var.get()
        username = self.ent_u.get()
        password = self.ent_p.get()
        token = self.ent_t.get()

        headers_str = self.headers_text.get("1.0", tk.END).strip()
        body_str = self.body_text.get("1.0", tk.END).strip()

        self.req_sent_text.delete("1.0", tk.END)
        self.resp_recv_text.delete("1.0", tk.END)

        # Clean previous visual container
        for child in self.render_container.winfo_children():
            child.destroy()

        self.req_sent_text.insert(tk.END, f"METHOD: {method}\n")
        self.req_sent_text.insert(tk.END, f"URL: {url}\n\n")
        self.req_sent_text.insert(tk.END, f"HEADERS SENT:\n{headers_str}\n\n")
        self.req_sent_text.insert(tk.END, f"BODY SENT:\n{body_str}\n")

        def run():
            try:
                resp = ReplayEngine.execute(
                    method=method,
                    url=url,
                    headers=headers_str,
                    body=body_str,
                    auth_type=auth_type,
                    username=username,
                    password=password,
                    token=token
                )

                # Display Results in UI safely
                self.app.after(0, lambda: self.show_results(resp))

                # Auto record call to Capture Traffic logs if matching filter
                self.app.after(0, lambda: self.app.check_and_capture(
                    method=method,
                    url=url,
                    req_headers=headers_str,
                    req_body=body_str,
                    status_code=resp.status_code,
                    resp_headers=dict(resp.headers),
                    resp_body=resp.content
                ))
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror("Request Failed", f"Failed to execute Custom call:\n{str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def show_results(self, resp):
        self.resp_recv_text.delete("1.0", tk.END)
        headers_str = json.dumps(dict(resp.headers), indent=2)
        body_val = resp.content.decode("utf-8", errors="ignore")

        self.resp_recv_text.insert(tk.END, f"STATUS CODE: {resp.status_code}\n\n")
        self.resp_recv_text.insert(tk.END, f"HEADERS RECEIVED:\n{headers_str}\n\n")
        self.resp_recv_text.insert(tk.END, f"BODY RECEIVED:\n{body_val}\n")

        TKHTMLRenderer.render(self.render_container, resp.content, "custom_sender")


# Replay Log Table UI and controller
class CSVReplayFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=5)
        self.app = app
        self.create_widgets()

    def create_widgets(self):
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        controls = ttk.Frame(paned, padding=10)
        paned.add(controls, weight=1)

        # Row 1 Actions
        r1 = ttk.Frame(controls)
        r1.pack(fill="x", pady=2)
        ttk.Button(r1, text="📁 UPLOAD CSV", command=self.upload_csv).pack(side="left", padx=5)

        self.btn_replay_selected = ttk.Button(r1, text="▶ Replay Selected", style="Accent.TButton", command=self.replay_selected)
        self.btn_replay_selected.pack(side="left", padx=5)

        ttk.Button(r1, text="▶▶ Replay All", command=self.replay_all).pack(side="left", padx=5)
        ttk.Button(r1, text="📥 Export Results to CSV", command=self.export_results).pack(side="left", padx=5)

        # Row 2 Auth Selection
        r2 = ttk.Frame(controls)
        r2.pack(fill="x", pady=5)
        ttk.Label(r2, text="Replay Auth:").pack(side="left", padx=2)
        self.auth_var = tk.StringVar(value="No Auth")
        auth_types = ["No Auth", "NTLM", "Basic Auth", "Bearer Token"]
        self.auth_cb = ttk.Combobox(r2, textvariable=self.auth_var, values=auth_types, state="readonly", width=15, font=(Theme.FONT_FAMILY, 10))
        self.auth_cb.pack(side="left", padx=5)
        self.auth_cb.bind("<<ComboboxSelected>>", self.on_auth_change)

        self.auth_inputs = ttk.Frame(r2)
        self.auth_inputs.pack(side="left", fill="x", padx=10)

        self.lbl_u = ttk.Label(self.auth_inputs, text="User:")
        self.ent_u = ttk.Entry(self.auth_inputs, width=15, font=(Theme.FONT_FAMILY, 10))
        self.lbl_p = ttk.Label(self.auth_inputs, text="Pass:")
        self.ent_p = ttk.Entry(self.auth_inputs, show="*", width=15, font=(Theme.FONT_FAMILY, 10))
        self.lbl_t = ttk.Label(self.auth_inputs, text="Token:")
        self.ent_t = ttk.Entry(self.auth_inputs, width=25, font=(Theme.FONT_FAMILY, 10))
        self.update_auth_inputs_visibility()

        # Mid Table
        table_card = ttk.LabelFrame(paned, text="CSV Loaded Records", padding=5)
        paned.add(table_card, weight=3)

        cols = ("id", "method", "url", "orig_status", "status")
        self.tree = ttk.Treeview(table_card, columns=cols, show="headings", height=8)
        self.tree.heading("id", text="ID")
        self.tree.heading("method", text="Method")
        self.tree.heading("url", text="URL")
        self.tree.heading("orig_status", text="Original Status")
        self.tree.heading("status", text="Replay Status")

        self.tree.column("id", width=50, minwidth=40, stretch=False)
        self.tree.column("method", width=80, minwidth=60, stretch=False)
        self.tree.column("url", width=500, minwidth=200, stretch=True)
        self.tree.column("orig_status", width=120, minwidth=80, stretch=False)
        self.tree.column("status", width=120, minwidth=80, stretch=False)

        self.tree.pack(side="top", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # Context menu bind
        self.ctx_menu = tk.Menu(self, tearoff=0, font=(Theme.FONT_FAMILY, 10))
        self.ctx_menu.add_command(label="🚀 Send to Custom API Sender", command=self.send_to_custom)
        self.ctx_menu.add_command(label="▶ Replay Request", command=self.replay_selected)
        self.tree.bind("<Button-3>", lambda e: self.app.show_context_menu(e, self.tree, self.ctx_menu))

        # Pagination
        pag = ttk.Frame(table_card)
        pag.pack(fill="x", pady=2)
        ttk.Button(pag, text="◀ Previous", command=self.prev_page).pack(side="left", padx=5)
        self.lbl_page = ttk.Label(pag, text="Page 1 of 1", font=(Theme.FONT_FAMILY, 10, "bold"))
        self.lbl_page.pack(side="left", padx=10)
        ttk.Button(pag, text="Next ▶", command=self.next_page).pack(side="left", padx=5)

        # Details tab notebook
        details = ttk.Notebook(paned)
        paned.add(details, weight=4)

        self.req_frame = ttk.Frame(details, padding=5)
        details.add(self.req_frame, text="📄 Request Details")
        self.req_text = tk.Text(self.req_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        self.req_text.pack(fill="both", expand=True)

        self.resp_frame = ttk.Frame(details, padding=5)
        details.add(self.resp_frame, text="📄 Response Details")
        self.resp_text = tk.Text(self.resp_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        self.resp_text.pack(fill="both", expand=True)

        self.render_tab = ttk.Frame(details, padding=5)
        details.add(self.render_tab, text="🎨 Render Visual")
        self.render_container = ttk.Frame(self.render_tab)
        self.render_container.pack(fill="both", expand=True)

    def on_auth_change(self, event=None):
        self.update_auth_inputs_visibility()

    def update_auth_inputs_visibility(self):
        self.lbl_u.pack_forget()
        self.ent_u.pack_forget()
        self.lbl_p.pack_forget()
        self.ent_p.pack_forget()
        self.lbl_t.pack_forget()
        self.ent_t.pack_forget()

        auth_type = self.auth_var.get()
        if auth_type == "Basic Auth" or auth_type == "NTLM":
            self.lbl_u.pack(side="left", padx=2)
            self.ent_u.pack(side="left", padx=5)
            self.lbl_p.pack(side="left", padx=2)
            self.ent_p.pack(side="left", padx=5)
        elif auth_type == "Bearer Token":
            self.lbl_t.pack(side="left", padx=2)
            self.ent_t.pack(side="left", padx=5)

    def upload_csv(self):
        filepath = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if not filepath:
            return

        try:
            self.app.replay_requests.clear()
            with open(filepath, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    req_h = {}
                    try:
                        req_h = json.loads(row.get("request_headers", "{}"))
                    except Exception:
                        pass

                    resp_h = {}
                    try:
                        resp_h = json.loads(row.get("response_headers", "{}"))
                    except Exception:
                        pass

                    req_item = build_traffic_record(
                        record_id=i + 1,
                        method=row.get("method", "GET"),
                        url=row.get("url", ""),
                        req_headers=req_h,
                        req_body=row.get("request_body", "").encode("utf-8"),
                        status_code="",  # Fill on replay
                        resp_headers=resp_h,
                        resp_body=row.get("response_body", "").encode("utf-8")
                    )
                    req_item["orig_status"] = row.get("status_code", "0")
                    self.app.replay_requests.append(req_item)

            self.app.replay_page = 0
            self.update_table()
            messagebox.showinfo("Loaded CSV", f"Successfully loaded {len(self.app.replay_requests)} requests.")
        except Exception as e:
            messagebox.showerror("Upload Error", f"Failed to parse CSV:\n{str(e)}")

    def update_table(self):
        for child in self.tree.get_children():
            self.tree.delete(child)

        start = self.app.replay_page * self.app.replay_page_size
        end = start + self.app.replay_page_size
        page_items = self.app.replay_requests[start:end]

        for item in page_items:
            status = item.get("status_code", "")
            orig_status = item.get("orig_status", "0")
            tag = classify_status(status) if status else "neutral"

            self.tree.insert(
                "", "end",
                iid=item["id"],
                values=(item["id"], item["method"], item["url"], orig_status, status if status else "Pending..."),
                tags=(tag,)
            )

        self.tree.tag_configure("success", foreground=Theme.COLOR_SUCCESS)
        self.tree.tag_configure("redirect", foreground=Theme.COLOR_REDIRECT)
        self.tree.tag_configure("error", foreground=Theme.COLOR_ERROR)
        self.tree.tag_configure("neutral", foreground=Theme.FG_MUTED)

        total_pages = max(1, (len(self.app.replay_requests) + self.app.replay_page_size - 1) // self.app.replay_page_size)
        self.lbl_page.config(text=f"Page {self.app.replay_page + 1} of {total_pages}")

    def prev_page(self):
        if self.app.replay_page > 0:
            self.app.replay_page -= 1
            self.update_table()

    def next_page(self):
        total_pages = max(1, (len(self.app.replay_requests) + self.app.replay_page_size - 1) // self.app.replay_page_size)
        if self.app.replay_page < total_pages - 1:
            self.app.replay_page += 1
            self.update_table()

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item_id = int(sel[0])
        item = next((x for x in self.app.replay_requests if x["id"] == item_id), None)
        self.app.selected_replay_item = item

        if item:
            self.app.display_request_details(item, self.req_text)
            self.app.display_response_details(item, self.resp_text)

            for child in self.render_container.winfo_children():
                child.destroy()
            TKHTMLRenderer.render(self.render_container, item.get("response_body", ""), "replay")

    def replay_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Empty Selection", "Select a request from the loaded table first.")
            return

        item_id = int(sel[0])
        item = next((x for x in self.app.replay_requests if x["id"] == item_id), None)
        if not item:
            return

        auth_type = self.auth_var.get()
        username = self.ent_u.get()
        password = self.ent_p.get()
        token = self.ent_t.get()

        def run():
            try:
                resp = ReplayEngine.execute(
                    method=item["method"],
                    url=item["url"],
                    headers=item["request_headers"],
                    body=item["request_body"],
                    auth_type=auth_type,
                    username=username,
                    password=password,
                    token=token
                )
                item["status_code"] = str(resp.status_code)
                item["response_headers"] = dict(resp.headers)
                item["response_body"] = resp.content

                self.app.after(0, lambda: self.update_table())
                self.app.after(0, lambda: self.tree.selection_set(item["id"]))
                self.app.after(0, lambda: self.on_select(None))
                self.app.after(0, lambda: messagebox.showinfo("Replay Done", f"Replay succeeded. Status: {resp.status_code}"))
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror("Replay Error", f"Failed to replay request:\n{str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def replay_all(self):
        if not self.app.replay_requests:
            messagebox.showwarning("List Empty", "No requests loaded to replay.")
            return

        auth_type = self.auth_var.get()
        username = self.ent_u.get()
        password = self.ent_p.get()
        token = self.ent_t.get()

        def run():
            success_count = 0
            for item in self.app.replay_requests:
                try:
                    resp = ReplayEngine.execute(
                        method=item["method"],
                        url=item["url"],
                        headers=item["request_headers"],
                        body=item["request_body"],
                        auth_type=auth_type,
                        username=username,
                        password=password,
                        token=token
                    )
                    item["status_code"] = str(resp.status_code)
                    item["response_headers"] = dict(resp.headers)
                    item["response_body"] = resp.content
                    success_count += 1
                    self.app.after(0, self.update_table)
                except Exception:
                    item["status_code"] = "Error"

            self.app.after(0, self.update_table)
            self.app.after(0, lambda: messagebox.showinfo("Replay All Done", f"Bulk replay completed. Succeeded {success_count} / {len(self.app.replay_requests)} calls."))

        threading.Thread(target=run, daemon=True).start()

    def export_results(self):
        if not self.app.replay_requests:
            messagebox.showwarning("Empty List", "No replay logs to export.")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if filepath:
            try:
                self.app.write_csv_file(filepath, self.app.replay_requests)
                messagebox.showinfo("Export Successful", "Replay results successfully exported to CSV.")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to save CSV:\n{str(e)}")

    def send_to_custom(self):
        sel = self.tree.selection()
        if not sel:
            return
        item_id = int(sel[0])
        item = next((x for x in self.app.replay_requests if x["id"] == item_id), None)
        if item:
            self.app.inbuilt_browser.populate_custom_sender_fields(item)


# Main WebInvader Application Orchestrator
class WebInvaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WebInvader — API Traffic Capturer v0.4")
        self.geometry("1200x800")
        self.configure(background=Theme.BG_MAIN)

        Theme.apply(self)

        # Load and Cache targets
        self.config = ConfigManager.load()
        self.targets = self.config.get("targets", [{"host": "http://localhost:13845", "pattern": "*"}])
        self.active_targets = list(self.targets)

        # In-memory queues and tables
        self.capture_queue = queue.Queue()
        self.captured_requests = []
        self.replay_requests = []

        # Selected trackers
        self.selected_capture_item = None
        self.selected_replay_item = None

        # Pagination
        self.capture_page = 0
        self.capture_page_size = 10
        self.replay_page = 0
        self.replay_page_size = 10

        # Background capturers
        self.proxy_running = False
        self.proxy_server = None
        self.playwright_running = False
        self.cdp_client = CDPClient(self)

        self.create_widgets()

        # Periodically poll queue
        self.after(100, self.process_capture_queue)

    def create_widgets(self):
        # Top banner panel
        banner = ttk.Frame(self, padding=10)
        banner.pack(fill="x")
        ttk.Label(banner, text="WebInvader — API Traffic Capturer", style="Title.TLabel").pack(side="left")
        ttk.Label(banner, text="  v0.4 [Light Modern Theme]", foreground=Theme.FG_MUTED).pack(side="left", padx=5)

        # Targets & Patterns Manager UI Panel
        self.setup_targets_panel()

        # Notebook with Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Tab 1 Capture Frame
        self.tab_capture = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_capture, text="🌐 CAPTURE & REPLAY")
        self.setup_capture_tab()

        # Tab 2 CSV Replay Frame
        self.csv_replay_frame = CSVReplayFrame(self.notebook, self)
        self.notebook.add(self.csv_replay_frame, text="🔄 CSV REPLAY")

        # Tab 3 Inbuilt Browser Custom Sender (Postman Lite)
        self.inbuilt_browser = InbuiltBrowserFrame(self.notebook, self)
        self.notebook.add(self.inbuilt_browser, text="🚀 CUSTOM SENDER")

        # Tab 4 Standalone RENDER Tab
        self.tab_render = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_render, text="🎨 RENDER")
        self.setup_render_tab()

    def setup_targets_panel(self):
        # Targets & Patterns Config Manager Frame
        lf_targets = ttk.LabelFrame(self, text="🎯 Active Targets & Patterns Manager", padding=10)
        lf_targets.pack(fill="x", padx=10, pady=5)

        # Left side inputs
        lf_inputs = ttk.Frame(lf_targets)
        lf_inputs.pack(side="left", fill="both", expand=True)

        row1 = ttk.Frame(lf_inputs)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="Target Host URL:", width=15).pack(side="left")
        self.target_host_entry = ttk.Entry(row1, width=35, font=(Theme.FONT_FAMILY, 10))
        self.target_host_entry.insert(0, "http://localhost:13845")
        self.target_host_entry.pack(side="left", padx=5)

        row2 = ttk.Frame(lf_inputs)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="URL Pattern:", width=15).pack(side="left")
        self.pattern_entry = ttk.Entry(row2, width=35, font=(Theme.FONT_FAMILY, 10))
        self.pattern_entry.insert(0, "*")
        self.pattern_entry.pack(side="left", padx=5)

        row3 = ttk.Frame(lf_inputs)
        row3.pack(fill="x", pady=5)
        self.btn_add_target = ttk.Button(row3, text="➕ Add Target Filter", style="Accent.TButton", command=self.add_target)
        self.btn_add_target.pack(side="left", padx=5)
        self.btn_remove_target = ttk.Button(row3, text="❌ Remove Selected", command=self.remove_target)
        self.btn_remove_target.pack(side="left", padx=5)

        # Right side treeview list of active targets
        lf_view = ttk.Frame(lf_targets)
        lf_view.pack(side="right", fill="both", expand=True, padx=10)

        cols = ("host", "pattern")
        self.targets_tree = ttk.Treeview(lf_view, columns=cols, show="headings", height=3)
        self.targets_tree.heading("host", text="Target Host URL")
        self.targets_tree.heading("pattern", text="Pattern")
        self.targets_tree.column("host", width=250, minwidth=150, stretch=True)
        self.targets_tree.column("pattern", width=120, minwidth=80, stretch=False)
        self.targets_tree.pack(side="top", fill="both", expand=True)

        # Sync initial targets treeview list
        self.sync_targets_tree()

    def add_target(self):
        host = self.target_host_entry.get().strip()
        pattern = self.pattern_entry.get().strip()
        if not host or not pattern:
            messagebox.showwarning("Incomplete Inputs", "Host URL and Pattern fields must be completed.")
            return

        # Add and save
        self.targets.append({"host": host, "pattern": pattern})
        self.config["targets"] = self.targets
        ConfigManager.save(self.config)
        self.active_targets = list(self.targets)
        self.sync_targets_tree()

    def remove_target(self):
        sel = self.targets_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a target filter from the active list first.")
            return

        idx = int(sel[0])
        if len(self.targets) <= 1:
            messagebox.showwarning("Deletion Blocked", "At least one active target filter must remain configured.")
            return

        self.targets.pop(idx)
        self.config["targets"] = self.targets
        ConfigManager.save(self.config)
        self.active_targets = list(self.targets)
        self.sync_targets_tree()

    def sync_targets_tree(self):
        for child in self.targets_tree.get_children():
            self.targets_tree.delete(child)
        for i, target in enumerate(self.targets):
            self.targets_tree.insert("", "end", iid=str(i), values=(target["host"], target["pattern"]))

    def setup_capture_tab(self):
        paned = ttk.PanedWindow(self.tab_capture, orient="vertical")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        controls = ttk.Frame(paned, padding=10)
        paned.add(controls, weight=1)

        # Capture Options
        r1 = ttk.Frame(controls)
        r1.pack(fill="x", pady=5)
        ttk.Label(r1, text="Capture Mode:").pack(side="left", padx=2)
        self.capture_mode_var = tk.StringVar(value="Inbuilt Proxy (Port 8888)")
        modes = ["Inbuilt Proxy (Port 8888)", "Chrome CDP Browser", "Combined Capture (CDP + Proxy)"]
        self.capture_mode_cb = ttk.Combobox(r1, textvariable=self.capture_mode_var, values=modes, state="readonly", width=30, font=(Theme.FONT_FAMILY, 10))
        self.capture_mode_cb.pack(side="left", padx=5)

        self.btn_capture = ttk.Button(r1, text="🌐 CAPTURE", style="Accent.TButton", command=self.toggle_capture)
        self.btn_capture.pack(side="left", padx=15)

        ttk.Button(r1, text="🧹 Clear Table", command=self.clear_capture_table).pack(side="left", padx=5)
        ttk.Button(r1, text="📥 Export to CSV", command=self.export_capture_to_csv).pack(side="left", padx=5)

        # Mid Captured logs table
        table_card = ttk.LabelFrame(paned, text="Captured Traffic Logs", padding=5)
        paned.add(table_card, weight=3)

        cols = ("id", "method", "url", "status")
        self.capture_tree = ttk.Treeview(table_card, columns=cols, show="headings", height=8)
        self.capture_tree.heading("id", text="ID")
        self.capture_tree.heading("method", text="Method")
        self.capture_tree.heading("url", text="URL")
        self.capture_tree.heading("status", text="Status Code")

        self.capture_tree.column("id", width=50, minwidth=40, stretch=False)
        self.capture_tree.column("method", width=80, minwidth=60, stretch=False)
        self.capture_tree.column("url", width=600, minwidth=200, stretch=True)
        self.capture_tree.column("status", width=120, minwidth=80, stretch=False)

        self.capture_tree.pack(side="top", fill="both", expand=True)
        self.capture_tree.bind("<<TreeviewSelect>>", self.on_capture_select)

        # Right click Context menu setup
        self.capture_context_menu = tk.Menu(self, tearoff=0, font=(Theme.FONT_FAMILY, 10))
        self.capture_context_menu.add_command(label="🚀 Send to Custom API Sender", command=self.send_selected_capture_to_custom_sender)
        self.capture_context_menu.add_command(label="▶ Replay Request", command=self.replay_selected_capture)
        self.capture_tree.bind("<Button-3>", lambda e: self.show_context_menu(e, self.capture_tree, self.capture_context_menu))

        # Pagination panel
        pag_row = ttk.Frame(table_card)
        pag_row.pack(fill="x", pady=2)
        ttk.Button(pag_row, text="◀ Previous", command=self.prev_capture_page).pack(side="left", padx=5)
        self.lbl_cap_page = ttk.Label(pag_row, text="Page 1 of 1", font=(Theme.FONT_FAMILY, 10, "bold"))
        self.lbl_cap_page.pack(side="left", padx=10)
        ttk.Button(pag_row, text="Next ▶", command=self.next_capture_page).pack(side="left", padx=5)

        # Bottom detailed sub-tabs
        details_card = ttk.Notebook(paned)
        paned.add(details_card, weight=4)

        self.cap_req_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.cap_req_frame, text="📄 Request Details")
        self.cap_req_text = tk.Text(self.cap_req_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        self.cap_req_text.pack(fill="both", expand=True)

        self.cap_resp_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.cap_resp_frame, text="📄 Response Details")
        self.cap_resp_text = tk.Text(self.cap_resp_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        self.cap_resp_text.pack(fill="both", expand=True)

        self.cap_render_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.cap_render_frame, text="🎨 Render Visual")
        self.cap_render_container = ttk.Frame(self.cap_render_frame)
        self.cap_render_container.pack(fill="both", expand=True)

    def setup_render_tab(self):
        self.render_controls = ttk.Frame(self.tab_render, padding=10)
        self.render_controls.pack(fill="x")

        ttk.Label(self.render_controls, text="Render Option:").pack(side="left", padx=2)
        self.render_mode_var = tk.StringVar(value="URL")
        modes = ["URL", "Raw HTML Code"]
        self.render_mode_cb = ttk.Combobox(self.render_controls, textvariable=self.render_mode_var, values=modes, state="readonly", width=15, font=(Theme.FONT_FAMILY, 10))
        self.render_mode_cb.pack(side="left", padx=5)
        self.render_mode_cb.bind("<<ComboboxSelected>>", self.on_render_mode_change)

        self.render_input_frame = ttk.Frame(self.render_controls)
        self.render_input_frame.pack(side="left", fill="x", expand=True, padx=5)

        self.lbl_render_url = ttk.Label(self.render_input_frame, text="URL:")
        self.lbl_render_url.pack(side="left", padx=2)
        self.ent_render_url = ttk.Entry(self.render_input_frame, font=(Theme.FONT_FAMILY, 10))
        self.ent_render_url.insert(0, "http://localhost:13845/")
        self.ent_render_url.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_render_go = ttk.Button(self.render_controls, text="🎨 Go & Render", style="Accent.TButton", command=self.go_and_render)
        self.btn_render_go.pack(side="right", padx=5)

        self.render_html_text_frame = ttk.Frame(self.tab_render, padding=5)
        self.render_html_text = tk.Text(self.render_html_text_frame, wrap="word", height=8, background="#ffffff", relief="flat", borderwidth=1, font=(Theme.FONT_FAMILY, 10))
        self.render_html_text.pack(fill="both", expand=True)

        self.render_view_frame = ttk.LabelFrame(self.tab_render, text="Inbuilt Browser Rendering View", padding=5)
        self.render_view_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.main_render_container = ttk.Frame(self.render_view_frame)
        self.main_render_container.pack(fill="both", expand=True)

    def on_render_mode_change(self, event=None):
        mode = self.render_mode_var.get()
        if mode == "URL":
            self.render_html_text_frame.pack_forget()
            self.lbl_render_url.pack(side="left", padx=2)
            self.ent_render_url.pack(side="left", fill="x", expand=True, padx=5)
        else:
            self.lbl_render_url.pack_forget()
            self.ent_render_url.pack_forget()
            self.render_html_text_frame.pack(fill="x", after=self.render_controls, pady=5)

    def show_context_menu(self, event, tree, menu):
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            menu.post(event.x_root, event.y_root)

    def toggle_capture(self):
        if self.proxy_running or self.playwright_running:
            self.stop_all_captures()
            self.btn_capture.config(text="🌐 CAPTURE", style="Accent.TButton")
        else:
            # Cache active entries thread-safe before initiating backend
            self.active_targets = list(self.targets)

            # Save configuration state locally
            self.config["targets"] = self.active_targets
            ConfigManager.save(self.config)

            mode = self.capture_mode_var.get()
            self.btn_capture.config(text="STOPPING...", state="disabled")
            if mode == "Inbuilt Proxy (Port 8888)":
                self.start_proxy()
            elif mode == "Chrome CDP Browser":
                self.start_playwright()
            else:
                # Combined Capture (CDP + Proxy): Runs both captures simultaneously to listen the complete local packet flows
                self.start_proxy()
                self.start_playwright()
            self.btn_capture.config(text="⏹ STOP CAPTURE", style="Accent.TButton", state="normal")

    def start_proxy(self):
        self.proxy_server = InbuiltProxyServer(self)
        self.proxy_server.start()
        self.proxy_running = True

    def start_playwright(self):
        self.playwright_running = True
        self.cdp_client.start()
        messagebox.showinfo("CDP Active", "Chrome CDP Browser controller launching...\nNavigate and trigger requests to capture traffic.")

    def stop_all_captures(self):
        if self.proxy_running and self.proxy_server:
            self.proxy_server.stop()
            self.proxy_running = False
            messagebox.showinfo("Proxy Stopped", "Built-in Proxy server shutdown cleanly.")
        if self.playwright_running:
            self.cdp_client.stop()
            self.playwright_running = False

    def check_and_capture(self, method, url, req_headers, req_body, status_code, resp_headers, resp_body):
        # Match against active targets list
        if not matches_filter(url, self.active_targets):
            return

        # Deduplication skipping identical requests
        record_hash = make_record_hash(url, method, req_body, status_code)
        for item in self.captured_requests:
            item_hash = make_record_hash(item["url"], item["method"], item["request_body"], item["status_code"])
            if item_hash == record_hash:
                return

        new_id = len(self.captured_requests) + 1
        record = build_traffic_record(new_id, method, url, req_headers, req_body, status_code, resp_headers, resp_body)
        self.capture_queue.put(record)

    def process_capture_queue(self):
        while not self.capture_queue.empty():
            item = self.capture_queue.get()
            self.captured_requests.append(item)
            self.update_capture_table()
        self.after(100, self.process_capture_queue)

    def update_capture_table(self):
        for child in self.capture_tree.get_children():
            self.capture_tree.delete(child)

        start = self.capture_page * self.capture_page_size
        end = start + self.capture_page_size
        page_items = self.captured_requests[start:end]

        for item in page_items:
            status = item.get("status_code", 0)
            tag = classify_status(status)
            self.capture_tree.insert(
                "", "end",
                iid=item["id"],
                values=(item["id"], item["method"], item["url"], status),
                tags=(tag,)
            )

        self.capture_tree.tag_configure("success", foreground=Theme.COLOR_SUCCESS)
        self.capture_tree.tag_configure("redirect", foreground=Theme.COLOR_REDIRECT)
        self.capture_tree.tag_configure("error", foreground=Theme.COLOR_ERROR)

        total_pages = max(1, (len(self.captured_requests) + self.capture_page_size - 1) // self.capture_page_size)
        self.lbl_cap_page.config(text=f"Page {self.capture_page + 1} of {total_pages}")

    def prev_capture_page(self):
        if self.capture_page > 0:
            self.capture_page -= 1
            self.update_capture_table()

    def next_capture_page(self):
        total_pages = max(1, (len(self.captured_requests) + self.capture_page_size - 1) // self.capture_page_size)
        if self.capture_page < total_pages - 1:
            self.capture_page += 1
            self.update_capture_table()

    def on_capture_select(self, event):
        sel = self.capture_tree.selection()
        if not sel:
            return
        item_id = int(sel[0])
        self.selected_capture_item = next((x for x in self.captured_requests if x["id"] == item_id), None)

        if self.selected_capture_item:
            self.display_request_details(self.selected_capture_item, self.cap_req_text)
            self.display_response_details(self.selected_capture_item, self.cap_resp_text)

            # Update Render visual panel
            for child in self.cap_render_container.winfo_children():
                child.destroy()
            TKHTMLRenderer.render(self.cap_render_container, self.selected_capture_item.get("response_body", ""), "capture")

    def display_request_details(self, item, text_widget):
        text_widget.delete("1.0", tk.END)
        headers_str = ReplayEngine.format_headers(item.get("request_headers", {}))

        body_val = item.get("request_body", "")
        if isinstance(body_val, bytes):
            body_val = body_val.decode("utf-8", errors="ignore")

        text_widget.insert(tk.END, f"METHOD: {item.get('method')}\n")
        text_widget.insert(tk.END, f"URL: {item.get('url')}\n\n")
        text_widget.insert(tk.END, f"HEADERS:\n{headers_str}\n\n")
        text_widget.insert(tk.END, f"BODY:\n{body_val}\n")

    def display_response_details(self, item, text_widget):
        text_widget.delete("1.0", tk.END)
        headers_str = ReplayEngine.format_headers(item.get("response_headers", {}))

        body_val = item.get("response_body", "")
        if isinstance(body_val, bytes):
            body_val = body_val.decode("utf-8", errors="ignore")

        text_widget.insert(tk.END, f"STATUS CODE: {item.get('status_code')}\n\n")
        text_widget.insert(tk.END, f"HEADERS:\n{headers_str}\n\n")
        text_widget.insert(tk.END, f"BODY:\n{body_val}\n")

    def clear_capture_table(self):
        self.captured_requests.clear()
        self.capture_page = 0
        self.update_capture_table()
        self.cap_req_text.delete("1.0", tk.END)
        self.cap_resp_text.delete("1.0", tk.END)
        for child in self.cap_render_container.winfo_children():
            child.destroy()

    def write_csv_file(self, filepath, request_list):
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["method", "url", "request_headers", "request_body", "status_code", "response_headers", "response_body"])
            for item in request_list:
                req_h = json.dumps(item.get("request_headers", {}))
                resp_h = json.dumps(item.get("response_headers", {}))

                req_body = item.get("request_body", "")
                if isinstance(req_body, bytes):
                    req_body = req_body.decode("utf-8", errors="ignore")
                resp_body = item.get("response_body", "")
                if isinstance(resp_body, bytes):
                    resp_body = resp_body.decode("utf-8", errors="ignore")

                writer.writerow([
                    item.get("method", ""),
                    item.get("url", ""),
                    req_h,
                    req_body,
                    item.get("status_code", ""),
                    resp_h,
                    resp_body
                ])

    def export_capture_to_csv(self):
        if not self.captured_requests:
            messagebox.showwarning("Empty List", "No captured requests logs to export.")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if filepath:
            try:
                self.write_csv_file(filepath, self.captured_requests)
                messagebox.showinfo("Export Done", "Traffic logs exported successfully.")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export CSV file:\n{str(e)}")

    def send_selected_capture_to_custom_sender(self):
        sel = self.capture_tree.selection()
        if not sel:
            return
        item_id = int(sel[0])
        item = next((x for x in self.captured_requests if x["id"] == item_id), None)
        if item:
            self.inbuilt_browser.populate_custom_sender_fields(item)

    def replay_selected_capture(self):
        sel = self.capture_tree.selection()
        if not sel:
            messagebox.showwarning("Empty Selection", "Select a request row from the captured table first.")
            return
        item_id = int(sel[0])
        item = next((x for x in self.captured_requests if x["id"] == item_id), None)
        if not item:
            return

        def run():
            try:
                resp = ReplayEngine.execute(
                    method=item["method"],
                    url=item["url"],
                    headers=item["request_headers"],
                    body=item["request_body"],
                    auth_type="No Auth"
                )
                item["status_code"] = resp.status_code
                item["response_headers"] = dict(resp.headers)
                item["response_body"] = resp.content

                self.after(0, lambda: self.update_capture_table())
                self.after(0, lambda: self.capture_tree.selection_set(item["id"]))
                self.after(0, lambda: self.on_capture_select(None))
                self.after(0, lambda: messagebox.showinfo("Replay Done", f"Synchronous replay completed successfully. Status: {resp.status_code}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Replay Failed", f"Failed to execute replayer call:\n{str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def go_and_render(self):
        mode = self.render_mode_var.get()
        for child in self.main_render_container.winfo_children():
            child.destroy()

        if mode == "URL":
            url = self.ent_render_url.get().strip()
            if not url:
                return
            def run():
                try:
                    resp = requests.get(url, timeout=10)
                    self.after(0, lambda: TKHTMLRenderer.render(self.main_render_container, resp.content, "main_render"))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Fetch Error", f"Failed to retrieve URL data:\n{str(e)}"))
            threading.Thread(target=run, daemon=True).start()
        else:
            raw_html = self.render_html_text.get("1.0", tk.END)
            TKHTMLRenderer.render(self.main_render_container, raw_html, "main_render")


if __name__ == "__main__":
    app = WebInvaderApp()
    app.mainloop()
