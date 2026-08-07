import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import json
import csv
import queue
import urllib.parse
import traceback
import sys
import os
import socket
import select
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver
import requests
from requests.auth import HTTPBasicAuth

# Try importing requests_ntlm safely to prevent crash if not installed
try:
    from requests_ntlm import HttpNtlmAuth
    HAS_NTLM = True
except ImportError:
    HttpNtlmAuth = None  # Prevent AttributeError in test patching
    HAS_NTLM = False

# Optional tkinterweb import for HTML rendering
try:
    from tkinterweb import HtmlFrame
    HAS_TKINTERWEB = True
except ImportError:
    HAS_TKINTERWEB = False


class ModernStyle:
    # Modern light colors
    BG_MAIN = "#f8f9fa"
    BG_CARD = "#ffffff"
    FG_MAIN = "#212529"
    FG_MUTED = "#6c757d"
    ACCENT_COLOR = "#0d6efd"  # Bootstrap primary blue
    ACCENT_HOVER = "#0b5ed7"
    BORDER_COLOR = "#dee2e6"

    # Status colors
    COLOR_SUCCESS = "#198754"  # Green
    COLOR_REDIRECT = "#fd7e14" # Orange
    COLOR_ERROR = "#dc3545"    # Red

    FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "Helvetica"

    @classmethod
    def apply(cls, root):
        style = ttk.Style()
        style.theme_use("clam")

        # Configure overall style
        style.configure(".", font=(cls.FONT_FAMILY, 10), background=cls.BG_MAIN, foreground=cls.FG_MAIN)
        style.configure("TFrame", background=cls.BG_MAIN)
        style.configure("Card.TFrame", background=cls.BG_CARD, borderwidth=1, relief="solid")

        # Notebook styling
        style.configure("TNotebook", background=cls.BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", font=(cls.FONT_FAMILY, 10, "bold"), background=cls.BORDER_COLOR, padding=[12, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", cls.BG_CARD), ("active", cls.BG_MAIN)],
                  foreground=[("selected", cls.ACCENT_COLOR)])

        # Treeview styling
        style.configure("Treeview", font=(cls.FONT_FAMILY, 9), rowheight=24, background=cls.BG_CARD, fieldbackground=cls.BG_CARD)
        style.configure("Treeview.Heading", font=(cls.FONT_FAMILY, 10, "bold"), background=cls.BORDER_COLOR, foreground=cls.FG_MAIN, relief="flat")
        style.map("Treeview", background=[("selected", cls.ACCENT_COLOR)], foreground=[("selected", "#ffffff")])

        # Button styling
        style.configure("TButton", font=(cls.FONT_FAMILY, 9, "bold"), background=cls.BORDER_COLOR, borderwidth=0, padding=[10, 6])
        style.map("TButton",
                  background=[("active", cls.ACCENT_COLOR), ("selected", cls.ACCENT_COLOR)],
                  foreground=[("active", "#ffffff"), ("selected", "#ffffff")])

        # Accent button
        style.configure("Accent.TButton", font=(cls.FONT_FAMILY, 10, "bold"), background=cls.ACCENT_COLOR, foreground="#ffffff", padding=[12, 8])
        style.map("Accent.TButton", background=[("active", cls.ACCENT_HOVER)])

        # Label styling
        style.configure("TLabel", background=cls.BG_MAIN, foreground=cls.FG_MAIN)
        style.configure("Title.TLabel", font=(cls.FONT_FAMILY, 14, "bold"), foreground=cls.ACCENT_COLOR)
        style.configure("Section.TLabel", font=(cls.FONT_FAMILY, 11, "bold"), foreground=cls.FG_MAIN)

        # Entry styling
        style.configure("TEntry", padding=5)


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


class WebInvaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WebInvader — API Traffic Capturer v0.4")
        self.geometry("1200x800")
        self.configure(background=ModernStyle.BG_MAIN)

        ModernStyle.apply(self)

        # Queues and states
        self.capture_queue = queue.Queue()
        self.captured_requests = []  # List of dicts
        self.replay_requests = []    # List of dicts

        # Pagination states
        self.capture_page = 0
        self.capture_page_size = 10
        self.replay_page = 0
        self.replay_page_size = 10

        # Selected items trackers
        self.selected_capture_item = None
        self.selected_replay_item = None

        # Background workers state
        self.proxy_running = False
        self.proxy_server = None
        self.playwright_running = False

        # Setup UI
        self.create_widgets()

        # Check queue periodically
        self.after(100, self.process_capture_queue)

    def create_widgets(self):
        # Top banner
        banner = ttk.Frame(self, padding=10)
        banner.pack(fill="x")
        title_label = ttk.Label(banner, text="WebInvader — API Traffic Capturer", style="Title.TLabel")
        title_label.pack(side="left")
        subtitle_label = ttk.Label(banner, text="  v0.4 [Light Modern Theme]", style="TLabel")
        subtitle_label.pack(side="left", fill="y")

        # Main tabs
        self.main_notebook = ttk.Notebook(self)
        self.main_notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # 1. Capture & Replay Tab
        self.tab_capture = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_capture, text="🌐 CAPTURE & REPLAY")
        self.setup_capture_tab()

        # 2. CSV Replay Tab
        self.tab_csv_replay = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_csv_replay, text="🔄 CSV REPLAY")
        self.setup_csv_replay_tab()

        # 3. Custom API Sender (Postman Lite) Tab
        self.tab_custom_sender = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_custom_sender, text="🚀 CUSTOM REQUEST SENDER (Postman Lite)")
        self.setup_custom_sender_tab()

        # 4. Render Tab
        self.tab_render = ttk.Frame(self.main_notebook)
        self.main_notebook.add(self.tab_render, text="🎨 RENDER")
        self.setup_render_tab()

    def setup_capture_tab(self):
        paned = ttk.PanedWindow(self.tab_capture, orient="vertical")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # Top Controls Frame
        controls_card = ttk.Frame(paned, padding=10)
        paned.add(controls_card, weight=1)

        # Controls Row 1
        r1 = ttk.Frame(controls_card)
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="Target Host URL:").pack(side="left", padx=2)
        self.target_host_entry = ttk.Entry(r1, width=40)
        self.target_host_entry.insert(0, "http://localhost:13845")
        self.target_host_entry.pack(side="left", padx=5)

        ttk.Label(r1, text="URL Pattern (e.g. api/v2 or *):").pack(side="left", padx=10)
        self.pattern_entry = ttk.Entry(r1, width=25)
        self.pattern_entry.insert(0, "*")
        self.pattern_entry.pack(side="left", padx=5)

        # Controls Row 2
        r2 = ttk.Frame(controls_card)
        r2.pack(fill="x", pady=5)
        ttk.Label(r2, text="Capture Mode:").pack(side="left", padx=2)
        self.capture_mode_var = tk.StringVar(value="Inbuilt Proxy (Port 8888)")
        modes = ["Inbuilt Proxy (Port 8888)", "Chrome CDP Browser"]
        self.capture_mode_cb = ttk.Combobox(r2, textvariable=self.capture_mode_var, values=modes, state="readonly", width=25)
        self.capture_mode_cb.pack(side="left", padx=5)

        self.btn_capture = ttk.Button(r2, text="CAPTURE", style="Accent.TButton", command=self.toggle_capture)
        self.btn_capture.pack(side="left", padx=15)

        self.btn_clear_capture = ttk.Button(r2, text="🧹 Clear Table", command=self.clear_capture_table)
        self.btn_clear_capture.pack(side="left", padx=5)

        self.btn_export_capture = ttk.Button(r2, text="📥 Export to CSV", command=self.export_capture_to_csv)
        self.btn_export_capture.pack(side="left", padx=5)

        # Mid Treeview Frame (List of captured requests)
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

        # Context Menu for capture tree
        self.capture_context_menu = tk.Menu(self, tearoff=0)
        self.capture_context_menu.add_command(label="🚀 Send to Custom API Sender", command=self.send_selected_capture_to_custom_sender)
        self.capture_context_menu.add_command(label="▶ Replay Request", command=self.replay_selected_capture)
        self.capture_tree.bind("<Button-3>", lambda e: self.show_context_menu(e, self.capture_tree, self.capture_context_menu))

        # Table Pagination Row
        pag_row = ttk.Frame(table_card)
        pag_row.pack(fill="x", pady=2)
        self.btn_cap_prev = ttk.Button(pag_row, text="◀ Previous", command=self.prev_capture_page)
        self.btn_cap_prev.pack(side="left", padx=5)
        self.lbl_cap_page = ttk.Label(pag_row, text="Page 1 of 1")
        self.lbl_cap_page.pack(side="left", padx=10)
        self.btn_cap_next = ttk.Button(pag_row, text="Next ▶", command=self.next_capture_page)
        self.btn_cap_next.pack(side="left", padx=5)

        # Bottom Details Sub-Tabs (Request, Response, Render Visual)
        details_card = ttk.Notebook(paned)
        paned.add(details_card, weight=4)

        # Sub-tab: Request Details
        self.cap_req_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.cap_req_frame, text="📄 Request Details")
        self.cap_req_text = tk.Text(self.cap_req_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1)
        self.cap_req_text.pack(fill="both", expand=True)

        # Sub-tab: Response Details
        self.cap_resp_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.cap_resp_frame, text="📄 Response Details")
        self.cap_resp_text = tk.Text(self.cap_resp_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1)
        self.cap_resp_text.pack(fill="both", expand=True)

        # Sub-tab: Render Visual
        self.cap_render_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.cap_render_frame, text="🎨 Render Visual")
        self.setup_render_widget(self.cap_render_frame, "capture")

    def setup_csv_replay_tab(self):
        paned = ttk.PanedWindow(self.tab_csv_replay, orient="vertical")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # Top Controls Frame
        controls_card = ttk.Frame(paned, padding=10)
        paned.add(controls_card, weight=1)

        # Row 1: Actions
        r1 = ttk.Frame(controls_card)
        r1.pack(fill="x", pady=2)
        self.btn_upload_csv = ttk.Button(r1, text="📁 UPLOAD CSV", command=self.upload_csv)
        self.btn_upload_csv.pack(side="left", padx=5)

        self.btn_replay_selected = ttk.Button(r1, text="▶ Replay Selected", style="Accent.TButton", command=self.replay_selected_csv)
        self.btn_replay_selected.pack(side="left", padx=5)

        self.btn_replay_all = ttk.Button(r1, text="▶▶ Replay All", command=self.replay_all_csv)
        self.btn_replay_all.pack(side="left", padx=5)

        self.btn_export_replay = ttk.Button(r1, text="📥 Export Results to CSV", command=self.export_replay_to_csv)
        self.btn_export_replay.pack(side="left", padx=5)

        # Row 2: Auth settings
        r2 = ttk.Frame(controls_card)
        r2.pack(fill="x", pady=5)
        ttk.Label(r2, text="Replay Auth:").pack(side="left", padx=2)
        self.replay_auth_var = tk.StringVar(value="No Auth")
        auth_types = ["No Auth", "NTLM", "Basic Auth", "Bearer Token"]
        self.replay_auth_cb = ttk.Combobox(r2, textvariable=self.replay_auth_var, values=auth_types, state="readonly", width=15)
        self.replay_auth_cb.pack(side="left", padx=5)
        self.replay_auth_cb.bind("<<ComboboxSelected>>", self.on_replay_auth_change)

        # Auth Details frame (pack/unpack or grid)
        self.auth_inputs_frame = ttk.Frame(r2)
        self.auth_inputs_frame.pack(side="left", fill="x", padx=10)

        self.lbl_auth_u = ttk.Label(self.auth_inputs_frame, text="User:")
        self.ent_auth_u = ttk.Entry(self.auth_inputs_frame, width=15)
        self.lbl_auth_p = ttk.Label(self.auth_inputs_frame, text="Pass:")
        self.ent_auth_p = ttk.Entry(self.auth_inputs_frame, show="*", width=15)
        self.lbl_auth_t = ttk.Label(self.auth_inputs_frame, text="Token:")
        self.ent_auth_t = ttk.Entry(self.auth_inputs_frame, width=25)

        self.update_auth_inputs_visibility()

        # Mid Treeview Frame (Loaded CSV/Replayed requests)
        table_card = ttk.LabelFrame(paned, text="CSV Replay Status", padding=5)
        paned.add(table_card, weight=3)

        cols = ("id", "method", "url", "orig_status", "status")
        self.replay_tree = ttk.Treeview(table_card, columns=cols, show="headings", height=8)
        self.replay_tree.heading("id", text="ID")
        self.replay_tree.heading("method", text="Method")
        self.replay_tree.heading("url", text="URL")
        self.replay_tree.heading("orig_status", text="Original Status")
        self.replay_tree.heading("status", text="Replay Status")

        self.replay_tree.column("id", width=50, minwidth=40, stretch=False)
        self.replay_tree.column("method", width=80, minwidth=60, stretch=False)
        self.replay_tree.column("url", width=500, minwidth=200, stretch=True)
        self.replay_tree.column("orig_status", width=120, minwidth=80, stretch=False)
        self.replay_tree.column("status", width=120, minwidth=80, stretch=False)

        self.replay_tree.pack(side="top", fill="both", expand=True)
        self.replay_tree.bind("<<TreeviewSelect>>", self.on_replay_select)

        # Context Menu for replay tree
        self.replay_context_menu = tk.Menu(self, tearoff=0)
        self.replay_context_menu.add_command(label="🚀 Send to Custom API Sender", command=self.send_selected_replay_to_custom_sender)
        self.replay_context_menu.add_command(label="▶ Replay Selected", command=self.replay_selected_csv)
        self.replay_tree.bind("<Button-3>", lambda e: self.show_context_menu(e, self.replay_tree, self.replay_context_menu))

        # Table Pagination Row
        pag_row = ttk.Frame(table_card)
        pag_row.pack(fill="x", pady=2)
        self.btn_rep_prev = ttk.Button(pag_row, text="◀ Previous", command=self.prev_replay_page)
        self.btn_rep_prev.pack(side="left", padx=5)
        self.lbl_rep_page = ttk.Label(pag_row, text="Page 1 of 1")
        self.lbl_rep_page.pack(side="left", padx=10)
        self.btn_rep_next = ttk.Button(pag_row, text="Next ▶", command=self.next_replay_page)
        self.btn_rep_next.pack(side="left", padx=5)

        # Bottom Details Sub-Tabs (Request, Response, Render Visual)
        details_card = ttk.Notebook(paned)
        paned.add(details_card, weight=4)

        # Sub-tab: Request Details
        self.rep_req_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.rep_req_frame, text="📄 Request Details")
        self.rep_req_text = tk.Text(self.rep_req_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1)
        self.rep_req_text.pack(fill="both", expand=True)

        # Sub-tab: Response Details
        self.rep_resp_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.rep_resp_frame, text="📄 Response Details")
        self.rep_resp_text = tk.Text(self.rep_resp_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1)
        self.rep_resp_text.pack(fill="both", expand=True)

        # Sub-tab: Render Visual
        self.rep_render_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.rep_render_frame, text="🎨 Render Visual")
        self.setup_render_widget(self.rep_render_frame, "replay")

    def setup_custom_sender_tab(self):
        paned = ttk.PanedWindow(self.tab_custom_sender, orient="vertical")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        inputs_card = ttk.Frame(paned, padding=10)
        paned.add(inputs_card, weight=2)

        # Row 1: Method & URL
        r1 = ttk.Frame(inputs_card)
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="Method:").pack(side="left", padx=2)
        self.cs_method_var = tk.StringVar(value="GET")
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
        self.cs_method_cb = ttk.Combobox(r1, textvariable=self.cs_method_var, values=methods, state="readonly", width=10)
        self.cs_method_cb.pack(side="left", padx=5)

        ttk.Label(r1, text="URL:").pack(side="left", padx=10)
        self.cs_url_entry = ttk.Entry(r1, width=60)
        self.cs_url_entry.insert(0, "http://localhost:13845/")
        self.cs_url_entry.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_cs_send = ttk.Button(r1, text="SEND REQUEST 🚀", style="Accent.TButton", command=self.send_custom_request)
        self.btn_cs_send.pack(side="right", padx=5)

        # Row 2: Auth
        r2 = ttk.Frame(inputs_card)
        r2.pack(fill="x", pady=5)
        ttk.Label(r2, text="Auth Type:").pack(side="left", padx=2)
        self.cs_auth_var = tk.StringVar(value="None")
        auth_types = ["None", "NTLM", "Basic Auth", "Bearer Token"]
        self.cs_auth_cb = ttk.Combobox(r2, textvariable=self.cs_auth_var, values=auth_types, state="readonly", width=12)
        self.cs_auth_cb.pack(side="left", padx=5)
        self.cs_auth_cb.bind("<<ComboboxSelected>>", self.on_cs_auth_change)

        # Auth inputs frame
        self.cs_auth_inputs_frame = ttk.Frame(r2)
        self.cs_auth_inputs_frame.pack(side="left", fill="x", padx=10)

        self.lbl_cs_auth_u = ttk.Label(self.cs_auth_inputs_frame, text="User:")
        self.ent_cs_auth_u = ttk.Entry(self.cs_auth_inputs_frame, width=15)
        self.lbl_cs_auth_p = ttk.Label(self.cs_auth_inputs_frame, text="Pass:")
        self.ent_cs_auth_p = ttk.Entry(self.cs_auth_inputs_frame, show="*", width=15)
        self.lbl_cs_auth_t = ttk.Label(self.cs_auth_inputs_frame, text="Token:")
        self.ent_cs_auth_t = ttk.Entry(self.cs_auth_inputs_frame, width=25)

        self.update_cs_auth_inputs_visibility()

        # Headers & Body inputs using a horizontal split
        r3 = ttk.Frame(inputs_card)
        r3.pack(fill="both", expand=True, pady=5)

        lf_headers = ttk.LabelFrame(r3, text="Headers (JSON or Key: Value per line)", padding=5)
        lf_headers.pack(side="left", fill="both", expand=True, padx=2)
        self.cs_headers_text = tk.Text(lf_headers, wrap="word", height=6, background="#ffffff", relief="flat", borderwidth=1)
        self.cs_headers_text.insert("1.0", '{\n  "Content-Type": "application/json"\n}')
        self.cs_headers_text.pack(fill="both", expand=True)

        lf_body = ttk.LabelFrame(r3, text="Body (Payload / POST Data)", padding=5)
        lf_body.pack(side="right", fill="both", expand=True, padx=2)
        self.cs_body_text = tk.Text(lf_body, wrap="word", height=6, background="#ffffff", relief="flat", borderwidth=1)
        self.cs_body_text.pack(fill="both", expand=True)

        # Bottom half details
        details_card = ttk.Notebook(paned)
        paned.add(details_card, weight=3)

        # Sub-tab: Request Sent
        self.cs_req_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.cs_req_frame, text="📄 Sent Request")
        self.cs_req_text = tk.Text(self.cs_req_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1)
        self.cs_req_text.pack(fill="both", expand=True)

        # Sub-tab: Response Received
        self.cs_resp_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.cs_resp_frame, text="📄 Received Response")
        self.cs_resp_text = tk.Text(self.cs_resp_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1)
        self.cs_resp_text.pack(fill="both", expand=True)

        # Sub-tab: Render Visual
        self.cs_render_frame = ttk.Frame(details_card, padding=5)
        details_card.add(self.cs_render_frame, text="🎨 Render Visual")
        self.setup_render_widget(self.cs_render_frame, "custom_sender")

    def setup_render_tab(self):
        self.render_controls = ttk.Frame(self.tab_render, padding=10)
        self.render_controls.pack(fill="x")

        ttk.Label(self.render_controls, text="Render Option:").pack(side="left", padx=2)
        self.render_mode_var = tk.StringVar(value="URL")
        modes = ["URL", "Raw HTML Code"]
        self.render_mode_cb = ttk.Combobox(self.render_controls, textvariable=self.render_mode_var, values=modes, state="readonly", width=15)
        self.render_mode_cb.pack(side="left", padx=5)
        self.render_mode_cb.bind("<<ComboboxSelected>>", self.on_render_mode_change)

        self.render_input_frame = ttk.Frame(self.render_controls)
        self.render_input_frame.pack(side="left", fill="x", expand=True, padx=5)

        self.lbl_render_url = ttk.Label(self.render_input_frame, text="URL:")
        self.lbl_render_url.pack(side="left", padx=2)
        self.ent_render_url = ttk.Entry(self.render_input_frame)
        self.ent_render_url.insert(0, "http://localhost:13845/")
        self.ent_render_url.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_render_go = ttk.Button(self.render_controls, text="Go & Render 🎨", style="Accent.TButton", command=self.go_and_render)
        self.btn_render_go.pack(side="right", padx=5)

        # Raw html area (initially hidden or collapsed)
        self.render_html_text_frame = ttk.Frame(self.tab_render, padding=5)
        self.render_html_text = tk.Text(self.render_html_text_frame, wrap="word", height=8, background="#ffffff", relief="flat", borderwidth=1)
        self.render_html_text.pack(fill="both", expand=True)

        # Inbuilt rendering area
        self.render_view_frame = ttk.LabelFrame(self.tab_render, text="Inbuilt Browser Rendering View", padding=5)
        self.render_view_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.setup_render_widget(self.render_view_frame, "main_render")

    def setup_render_widget(self, parent, target_name):
        if HAS_TKINTERWEB:
            try:
                frame = HtmlFrame(parent)
                frame.pack(fill="both", expand=True)
                setattr(self, f"render_widget_{target_name}", frame)
                setattr(self, f"render_widget_type_{target_name}", "html")
                return
            except Exception as e:
                print(f"Failed to load HtmlFrame: {e}. Falling back to Text rendering Widget.")

        fb_frame = ttk.Frame(parent)
        fb_frame.pack(fill="both", expand=True)
        lbl_info = ttk.Label(fb_frame, text="[Rendering Fallback Mode - Raw Text / Simple HTML parser]", foreground=ModernStyle.FG_MUTED)
        lbl_info.pack(anchor="nw", pady=2)

        txt = tk.Text(fb_frame, wrap="word", background="#ffffff", relief="flat", borderwidth=1)
        txt.pack(fill="both", expand=True)
        setattr(self, f"render_widget_{target_name}", txt)
        setattr(self, f"render_widget_type_{target_name}", "text")

    def display_rendered_html(self, target_name, html_content):
        widget = getattr(self, f"render_widget_{target_name}", None)
        wtype = getattr(self, f"render_widget_type_{target_name}", None)
        if not widget:
            return

        if wtype == "html":
            try:
                if isinstance(html_content, bytes):
                    html_content = html_content.decode("utf-8", errors="ignore")
                widget.load_html(html_content)
            except Exception as e:
                print(f"HtmlFrame render error: {e}")
        else:
            try:
                if isinstance(html_content, bytes):
                    html_content = html_content.decode("utf-8", errors="ignore")
                widget.delete("1.0", tk.END)
                widget.insert("1.0", html_content)
            except Exception as e:
                print(f"Text fallback render error: {e}")

    # Auth details visibility
    def on_replay_auth_change(self, event=None):
        self.update_auth_inputs_visibility()

    def update_auth_inputs_visibility(self):
        self.lbl_auth_u.pack_forget()
        self.ent_auth_u.pack_forget()
        self.lbl_auth_p.pack_forget()
        self.ent_auth_p.pack_forget()
        self.lbl_auth_t.pack_forget()
        self.ent_auth_t.pack_forget()

        auth_type = self.replay_auth_var.get()
        if auth_type == "NTLM" or auth_type == "Basic Auth":
            self.lbl_auth_u.pack(side="left", padx=2)
            self.ent_auth_u.pack(side="left", padx=5)
            self.lbl_auth_p.pack(side="left", padx=2)
            self.ent_auth_p.pack(side="left", padx=5)
        elif auth_type == "Bearer Token":
            self.lbl_auth_t.pack(side="left", padx=2)
            self.ent_auth_t.pack(side="left", padx=5)

    def on_cs_auth_change(self, event=None):
        self.update_cs_auth_inputs_visibility()

    def update_cs_auth_inputs_visibility(self):
        self.lbl_cs_auth_u.pack_forget()
        self.ent_cs_auth_u.pack_forget()
        self.lbl_cs_auth_p.pack_forget()
        self.ent_cs_auth_p.pack_forget()
        self.lbl_cs_auth_t.pack_forget()
        self.ent_cs_auth_t.pack_forget()

        auth_type = self.cs_auth_var.get()
        if auth_type == "NTLM" or auth_type == "Basic Auth":
            self.lbl_cs_auth_u.pack(side="left", padx=2)
            self.ent_cs_auth_u.pack(side="left", padx=5)
            self.lbl_cs_auth_p.pack(side="left", padx=2)
            self.ent_cs_auth_p.pack(side="left", padx=5)
        elif auth_type == "Bearer Token":
            self.lbl_cs_auth_t.pack(side="left", padx=2)
            self.ent_cs_auth_t.pack(side="left", padx=5)

    def on_render_mode_change(self, event=None):
        mode = self.render_mode_var.get()
        if mode == "URL":
            self.render_html_text_frame.pack_forget()
            self.lbl_render_url.pack(side="left", padx=2)
            self.ent_render_url.pack(side="left", fill="x", expand=True, padx=5)
        else:
            self.lbl_render_url.pack_forget()
            self.ent_render_url.pack_forget()
            # Correctly pack self.render_html_text_frame after self.render_controls, as they share the same parent self.tab_render!
            self.render_html_text_frame.pack(fill="x", after=self.render_controls, pady=5)

    def show_context_menu(self, event, tree, menu):
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            menu.post(event.x_root, event.y_root)

    # 2. CAPTURE AND PROXY BACKEND IMPLEMENTATION
    def toggle_capture(self):
        if self.proxy_running or self.playwright_running:
            # Stop capture
            self.stop_all_captures()
            self.btn_capture.config(text="CAPTURE", style="Accent.TButton")
        else:
            # Start capture
            mode = self.capture_mode_var.get()
            self.btn_capture.config(text="STOPPING...", state="disabled")
            if mode == "Inbuilt Proxy (Port 8888)":
                self.start_proxy()
            else:
                self.start_playwright()
            self.btn_capture.config(text="STOP CAPTURE", style="Accent.TButton", state="normal")

    def start_proxy(self):
        try:
            self.proxy_server = ThreadedHTTPServer(("127.0.0.1", 8888), ProxyHandler)
            self.proxy_server.app = self
            self.proxy_running = True
            self.proxy_thread = threading.Thread(target=self.proxy_server.serve_forever, daemon=True)
            self.proxy_thread.start()
            messagebox.showinfo("Proxy Started", "Inbuilt Proxy server is running on http://127.0.0.1:8888\nConfigure your application or system proxy to inspect traffic.")
        except Exception as e:
            self.proxy_running = False
            messagebox.showerror("Proxy Error", f"Failed to start proxy on port 8888:\n{str(e)}")

    def start_playwright(self):
        self.playwright_running = True
        self.playwright_thread = threading.Thread(target=self.run_playwright_loop, daemon=True)
        self.playwright_thread.start()
        messagebox.showinfo("Browser Launching", "Launching CDP Chrome Browser...\nClose the browser or click 'STOP CAPTURE' to stop.")

    def run_playwright_loop(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()

                # Event listener for response received
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

                        self.check_and_capture(
                            method=method,
                            url=url,
                            req_headers=req_headers,
                            req_body=req_body,
                            status_code=status,
                            resp_headers=resp_headers,
                            resp_body=resp_body
                        )
                    except Exception as ex:
                        print(f"Playwright callback handling error: {ex}")

                page.on("response", handle_response)

                # Pre-navigate to target host
                target_host = self.target_host_entry.get().strip()
                if target_host:
                    try:
                        page.goto(target_host)
                    except Exception:
                        pass

                # Keep loop alive while playwright_running is active
                while self.playwright_running:
                    # Brief poll sleep
                    try:
                        page.wait_for_timeout(100)
                    except Exception:
                        break

                browser.close()
        except ImportError:
            self.after(0, lambda: messagebox.showerror("Playwright Error", "Playwright library not installed or initialized.\nRun: playwright install"))
        except Exception as e:
            print(f"Playwright process error: {e}")
        finally:
            self.playwright_running = False
            self.after(0, lambda: self.btn_capture.config(text="CAPTURE", style="Accent.TButton"))

    def stop_all_captures(self):
        if self.proxy_running:
            if self.proxy_server:
                self.proxy_server.shutdown()
                self.proxy_server.server_close()
            self.proxy_running = False
            messagebox.showinfo("Proxy Stopped", "Inbuilt Proxy has been stopped.")
        if self.playwright_running:
            self.playwright_running = False

    def check_and_capture(self, method, url, req_headers, req_body, status_code, resp_headers, resp_body):
        # Filter matching logic
        target_host = self.target_host_entry.get().strip()
        pattern = self.pattern_entry.get().strip()

        parsed_target = urllib.parse.urlparse(target_host)
        parsed_url = urllib.parse.urlparse(url)

        target_match = False
        if parsed_target.netloc:
            if parsed_target.netloc.lower() in parsed_url.netloc.lower() or target_host.lower() in url.lower():
                target_match = True
        else:
            if target_host.lower() in url.lower():
                target_match = True

        if not target_match:
            return

        pattern_match = False
        if pattern == "*":
            pattern_match = True
        elif pattern.lower() in url.lower():
            pattern_match = True

        if not pattern_match:
            return

        # Duplicate detection (same URL + method + body + status)
        body_str = req_body
        if isinstance(body_str, bytes):
            body_str = body_str.decode("utf-8", errors="ignore")

        for item in self.captured_requests:
            item_body = item.get("request_body", "")
            if isinstance(item_body, bytes):
                item_body = item_body.decode("utf-8", errors="ignore")
            if (item["url"] == url and
                item["method"] == method and
                item_body == body_str and
                item["status_code"] == status_code):
                return

        new_id = len(self.captured_requests) + 1
        captured_item = {
            "id": new_id,
            "method": method,
            "url": url,
            "request_headers": req_headers,
            "request_body": req_body,
            "status_code": status_code,
            "response_headers": resp_headers,
            "response_body": resp_body
        }
        self.capture_queue.put(captured_item)

    def process_capture_queue(self):
        while not self.capture_queue.empty():
            item = self.capture_queue.get()
            self.captured_requests.append(item)
            self.update_capture_table()
        self.after(100, self.process_capture_queue)

    def clear_capture_table(self):
        self.captured_requests.clear()
        self.capture_page = 0
        self.update_capture_table()
        self.clear_capture_details_widgets()

    def clear_capture_details_widgets(self):
        self.cap_req_text.delete("1.0", tk.END)
        self.cap_resp_text.delete("1.0", tk.END)
        self.display_rendered_html("capture", "")

    # Pagination Capture logs
    def update_capture_table(self):
        for row in self.capture_tree.get_children():
            self.capture_tree.delete(row)

        start = self.capture_page * self.capture_page_size
        end = start + self.capture_page_size
        page_items = self.captured_requests[start:end]

        for item in page_items:
            status = item.get("status_code", 0)
            tag = "success"
            if 300 <= status < 400:
                tag = "redirect"
            elif status >= 400 or status == 0:
                tag = "error"

            self.capture_tree.insert(
                "", "end",
                iid=item["id"],
                values=(item["id"], item["method"], item["url"], status),
                tags=(tag,)
            )

        self.capture_tree.tag_configure("success", foreground=ModernStyle.COLOR_SUCCESS)
        self.capture_tree.tag_configure("redirect", foreground=ModernStyle.COLOR_REDIRECT)
        self.capture_tree.tag_configure("error", foreground=ModernStyle.COLOR_ERROR)

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
            self.display_rendered_html("capture", self.selected_capture_item.get("response_body", ""))

    # 3. REPLAY, NTLM, AND CSV IMPORT/EXPORT
    def display_request_details(self, item, text_widget):
        text_widget.delete("1.0", tk.END)
        headers_str = json.dumps(item.get("request_headers", {}), indent=2) if isinstance(item.get("request_headers"), (dict, list)) else str(item.get("request_headers", ""))

        body_val = item.get("request_body", "")
        if isinstance(body_val, bytes):
            body_val = body_val.decode("utf-8", errors="ignore")

        text_widget.insert(tk.END, f"METHOD: {item.get('method')}\n")
        text_widget.insert(tk.END, f"URL: {item.get('url')}\n\n")
        text_widget.insert(tk.END, f"HEADERS:\n{headers_str}\n\n")
        text_widget.insert(tk.END, f"BODY:\n{body_val}\n")

    def display_response_details(self, item, text_widget):
        text_widget.delete("1.0", tk.END)
        headers_str = json.dumps(item.get("response_headers", {}), indent=2) if isinstance(item.get("response_headers"), (dict, list)) else str(item.get("response_headers", ""))

        body_val = item.get("response_body", "")
        if isinstance(body_val, bytes):
            body_val = body_val.decode("utf-8", errors="ignore")

        text_widget.insert(tk.END, f"STATUS CODE: {item.get('status_code')}\n\n")
        text_widget.insert(tk.END, f"HEADERS:\n{headers_str}\n\n")
        text_widget.insert(tk.END, f"BODY:\n{body_val}\n")

    def run_http_request(self, method, url, headers, body, auth_type, username="", password="", token=""):
        # Format headers
        req_headers = {}
        if isinstance(headers, str):
            try:
                req_headers = json.loads(headers)
            except Exception:
                for line in headers.strip().split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        req_headers[k.strip()] = v.strip()
        elif isinstance(headers, dict):
            req_headers = headers

        # Determine authentication
        auth = None
        if auth_type == "Basic Auth":
            auth = HTTPBasicAuth(username, password)
        elif auth_type == "NTLM":
            if not HAS_NTLM:
                raise ImportError("requests-ntlm is not installed. Run: pip install requests-ntlm")
            auth = HttpNtlmAuth(username, password)
        elif auth_type == "Bearer Token":
            req_headers["Authorization"] = f"Bearer {token}"

        # If body is string, convert to bytes if it looks like JSON or form
        if isinstance(body, str):
            body = body.encode("utf-8")

        # Execute request synchronously
        resp = requests.request(
            method=method,
            url=url,
            headers=req_headers,
            data=body,
            auth=auth,
            allow_redirects=False,
            timeout=15
        )
        return resp

    def replay_selected_capture(self):
        # Allow instant replay of a selected row in the capture tab
        sel = self.capture_tree.selection()
        if not sel:
            messagebox.showwarning("Selection Empty", "Please select a request from the capture logs.")
            return
        item_id = int(sel[0])
        item = next((x for x in self.captured_requests if x["id"] == item_id), None)
        if not item:
            return

        def run_rep():
            try:
                resp = self.run_http_request(
                    method=item["method"],
                    url=item["url"],
                    headers=item["request_headers"],
                    body=item["request_body"],
                    auth_type="No Auth"
                )
                item["status_code"] = resp.status_code
                item["response_headers"] = dict(resp.headers)
                item["response_body"] = resp.content

                self.after(0, lambda: self.refresh_after_replay(item))
                self.after(0, lambda: messagebox.showinfo("Replay Done", f"Replayed request successfully. Status Code: {resp.status_code}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Replay Error", f"Failed to replay request:\n{str(e)}"))

        threading.Thread(target=run_rep, daemon=True).start()

    def refresh_after_replay(self, item):
        self.update_capture_table()
        # Reselect to load updated details
        self.capture_tree.selection_set(item["id"])
        self.on_capture_select(None)

    def upload_csv(self):
        filepath = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if not filepath:
            return

        try:
            self.replay_requests.clear()
            with open(filepath, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    # parse request headers
                    req_h = {}
                    try:
                        req_h = json.loads(row.get("request_headers", "{}"))
                    except Exception:
                        pass

                    # parse response headers
                    resp_h = {}
                    try:
                        resp_h = json.loads(row.get("response_headers", "{}"))
                    except Exception:
                        pass

                    req_item = {
                        "id": i + 1,
                        "method": row.get("method", "GET"),
                        "url": row.get("url", ""),
                        "request_headers": req_h,
                        "request_body": row.get("request_body", "").encode("utf-8"),
                        "orig_status": row.get("status_code", "0"),
                        "status_code": "",  # To fill on replay
                        "response_headers": resp_h,
                        "response_body": row.get("response_body", "").encode("utf-8")
                    }
                    self.replay_requests.append(req_item)

            self.replay_page = 0
            self.update_replay_table()
            messagebox.showinfo("Upload Complete", f"Successfully loaded {len(self.replay_requests)} requests from CSV.")
        except Exception as e:
            messagebox.showerror("Upload Error", f"Failed to parse CSV:\n{str(e)}")

    def update_replay_table(self):
        for row in self.replay_tree.get_children():
            self.replay_tree.delete(row)

        start = self.replay_page * self.replay_page_size
        end = start + self.replay_page_size
        page_items = self.replay_requests[start:end]

        for item in page_items:
            # Color based on replay status or original status
            status = item.get("status_code", "")
            orig_status = item.get("orig_status", "0")

            tag = "neutral"
            if status:
                try:
                    sc = int(status)
                    if 200 <= sc < 300:
                        tag = "success"
                    elif 300 <= sc < 400:
                        tag = "redirect"
                    else:
                        tag = "error"
                except Exception:
                    tag = "error"

            self.replay_tree.insert(
                "", "end",
                iid=item["id"],
                values=(item["id"], item["method"], item["url"], orig_status, status if status else "Pending..."),
                tags=(tag,)
            )

        self.replay_tree.tag_configure("success", foreground=ModernStyle.COLOR_SUCCESS)
        self.replay_tree.tag_configure("redirect", foreground=ModernStyle.COLOR_REDIRECT)
        self.replay_tree.tag_configure("error", foreground=ModernStyle.COLOR_ERROR)
        self.replay_tree.tag_configure("neutral", foreground=ModernStyle.FG_MUTED)

        total_pages = max(1, (len(self.replay_requests) + self.replay_page_size - 1) // self.replay_page_size)
        self.lbl_rep_page.config(text=f"Page {self.replay_page + 1} of {total_pages}")

    def prev_replay_page(self):
        if self.replay_page > 0:
            self.replay_page -= 1
            self.update_replay_table()

    def next_replay_page(self):
        total_pages = max(1, (len(self.replay_requests) + self.replay_page_size - 1) // self.replay_page_size)
        if self.replay_page < total_pages - 1:
            self.replay_page += 1
            self.update_replay_table()

    def on_replay_select(self, event):
        sel = self.replay_tree.selection()
        if not sel:
            return
        item_id = int(sel[0])
        self.selected_replay_item = next((x for x in self.replay_requests if x["id"] == item_id), None)

        if self.selected_replay_item:
            self.display_request_details(self.selected_replay_item, self.rep_req_text)
            self.display_response_details(self.selected_replay_item, self.rep_resp_text)
            self.display_rendered_html("replay", self.selected_replay_item.get("response_body", ""))

    def replay_selected_csv(self):
        sel = self.replay_tree.selection()
        if not sel:
            messagebox.showwarning("Selection Empty", "Please select a request from the replay status table.")
            return
        item_id = int(sel[0])
        item = next((x for x in self.replay_requests if x["id"] == item_id), None)
        if not item:
            return

        auth_type = self.replay_auth_var.get()
        username = self.ent_auth_u.get()
        password = self.ent_auth_p.get()
        token = self.ent_auth_t.get()

        def run_rep():
            try:
                resp = self.run_http_request(
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

                self.after(0, lambda: self.update_replay_table())
                self.after(0, lambda: self.replay_tree.selection_set(item["id"]))
                self.after(0, lambda: self.on_replay_select(None))
                self.after(0, lambda: messagebox.showinfo("Replay Done", f"Replayed successfully. Status: {resp.status_code}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Replay Error", f"Failed to replay request:\n{str(e)}"))

        threading.Thread(target=run_rep, daemon=True).start()

    def replay_all_csv(self):
        if not self.replay_requests:
            messagebox.showwarning("List Empty", "No requests loaded to replay.")
            return

        auth_type = self.replay_auth_var.get()
        username = self.ent_auth_u.get()
        password = self.ent_auth_p.get()
        token = self.ent_auth_t.get()

        def run_rep_all():
            success_count = 0
            for item in self.replay_requests:
                try:
                    resp = self.run_http_request(
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

                    # Periodic GUI update
                    self.after(0, self.update_replay_table)
                except Exception as e:
                    print(f"Replay all single item error: {e}")
                    item["status_code"] = "Error"

            self.after(0, self.update_replay_table)
            self.after(0, lambda: messagebox.showinfo("Replay All Done", f"Bulk Replay completed. Successfully replayed {success_count} / {len(self.replay_requests)} requests."))

        threading.Thread(target=run_rep_all, daemon=True).start()

    # CSV Exporters
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
            messagebox.showwarning("Export Empty", "No captured requests to export.")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if filepath:
            try:
                self.write_csv_file(filepath, self.captured_requests)
                messagebox.showinfo("Export Complete", "Captured traffic successfully exported to CSV.")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export capture:\n{str(e)}")

    def export_replay_to_csv(self):
        if not self.replay_requests:
            messagebox.showwarning("Export Empty", "No loaded replay requests to export.")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if filepath:
            try:
                self.write_csv_file(filepath, self.replay_requests)
                messagebox.showinfo("Export Complete", "Replay results successfully exported to CSV.")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export replay results:\n{str(e)}")

    # 4. CUSTOM API SENDER (POSTMAN LITE) & CONTEXT MENU
    def send_selected_capture_to_custom_sender(self):
        sel = self.capture_tree.selection()
        if not sel:
            return
        item_id = int(sel[0])
        item = next((x for x in self.captured_requests if x["id"] == item_id), None)
        if item:
            self.populate_custom_sender_fields(item)

    def send_selected_replay_to_custom_sender(self):
        sel = self.replay_tree.selection()
        if not sel:
            return
        item_id = int(sel[0])
        item = next((x for x in self.replay_requests if x["id"] == item_id), None)
        if item:
            self.populate_custom_sender_fields(item)

    def populate_custom_sender_fields(self, item):
        # Switch notebook to custom sender tab
        self.main_notebook.select(self.tab_custom_sender)

        # Populate URL & Method
        self.cs_method_var.set(item.get("method", "GET"))
        self.cs_url_entry.delete(0, tk.END)
        self.cs_url_entry.insert(0, item.get("url", ""))

        # Populate Headers
        headers = item.get("request_headers", {})
        self.cs_headers_text.delete("1.0", tk.END)
        if isinstance(headers, dict):
            self.cs_headers_text.insert("1.0", json.dumps(headers, indent=2))
        else:
            self.cs_headers_text.insert("1.0", str(headers))

        # Populate Body
        body = item.get("request_body", "")
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="ignore")
        self.cs_body_text.delete("1.0", tk.END)
        self.cs_body_text.insert("1.0", body)

        messagebox.showinfo("Custom Sender", "Selected request details have been sent to Custom Request Sender.")

    def send_custom_request(self):
        method = self.cs_method_var.get()
        url = self.cs_url_entry.get().strip()
        auth_type = self.cs_auth_var.get()
        username = self.ent_cs_auth_u.get()
        password = self.ent_cs_auth_p.get()
        token = self.ent_cs_auth_t.get()

        headers_str = self.cs_headers_text.get("1.0", tk.END).strip()
        body_str = self.cs_body_text.get("1.0", tk.END).strip()

        self.cs_req_text.delete("1.0", tk.END)
        self.cs_resp_text.delete("1.0", tk.END)
        self.display_rendered_html("custom_sender", "")

        # Show sent logs
        self.cs_req_text.insert(tk.END, f"METHOD: {method}\n")
        self.cs_req_text.insert(tk.END, f"URL: {url}\n\n")
        self.cs_req_text.insert(tk.END, f"AUTH TYPE: {auth_type}\n\n")
        self.cs_req_text.insert(tk.END, f"HEADERS SENT:\n{headers_str}\n\n")
        self.cs_req_text.insert(tk.END, f"BODY SENT:\n{body_str}\n")

        def run_cs():
            try:
                resp = self.run_http_request(
                    method=method,
                    url=url,
                    headers=headers_str,
                    body=body_str,
                    auth_type=auth_type,
                    username=username,
                    password=password,
                    token=token
                )

                # Show results
                self.after(0, lambda: self.show_custom_sender_results(resp))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Request Error", f"Failed to send request:\n{str(e)}"))

        threading.Thread(target=run_cs, daemon=True).start()

    def show_custom_sender_results(self, resp):
        self.cs_resp_text.delete("1.0", tk.END)
        headers_str = json.dumps(dict(resp.headers), indent=2)

        body_val = resp.content.decode("utf-8", errors="ignore")

        self.cs_resp_text.insert(tk.END, f"STATUS CODE: {resp.status_code}\n\n")
        self.cs_resp_text.insert(tk.END, f"HEADERS RECEIVED:\n{headers_str}\n\n")
        self.cs_resp_text.insert(tk.END, f"BODY RECEIVED:\n{body_val}\n")

        self.display_rendered_html("custom_sender", resp.content)

    def go_and_render(self):
        mode = self.render_mode_var.get()
        if mode == "URL":
            url = self.ent_render_url.get().strip()
            if not url:
                return
            def fetch_and_render():
                try:
                    resp = requests.get(url, timeout=10)
                    self.after(0, lambda: self.display_rendered_html("main_render", resp.content))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Render Error", f"Failed to fetch and render {url}:\n{str(e)}"))
            threading.Thread(target=fetch_and_render, daemon=True).start()
        else:
            raw_html = self.render_html_text.get("1.0", tk.END)
            self.display_rendered_html("main_render", raw_html)


if __name__ == "__main__":
    app = WebInvaderApp()
    app.mainloop()
