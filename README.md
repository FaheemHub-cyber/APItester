# WebInvader — API Traffic Capturer v0.4

A lightweight Python GUI application for HTTP traffic capture & replay supporting Chrome DevTools Protocol (CDP), CSV Upload & Replay, Custom API Request Sender (Postman Lite / Inbuilt Browser), and an Inbuilt Proxy Interceptor.

The application has been upgraded with a modern, clean light-theme interface, an integrated custom sender, and advanced pattern and rendering support.

---

## Key Features

- **Dedicated CSV Replay Tab**:
  - Upload exported CSV files (`webinvader_capture.csv` or standard HTTP request CSVs).
  - Inspect all loaded request/response records in a clean light-themed paginated table UI.
  - Replay individual requests (**Replay Selected**) or bulk-replay all requests (**Replay All**) manually with configurable Auth (No Auth, NTLM, Basic Auth, Bearer Token).
- **Multiple Capture Modes**:
  - **Inbuilt Proxy Server (Port 8888)** — Built-in HTTP proxy interceptor to capture traffic from any external browser, terminal, or application.
  - **Chrome CDP Browser** — Launches a live Chromium instance (using Playwright) with real-time network interception and packet capture.
- **Pattern & Host Filtering**:
  - Enter your **Target Host** (e.g. `http://localhost:13845`) and **URL Pattern** (e.g. `api/v2`).
  - Supports wildcard (`*`) to capture ALL requests and responses belonging to the target host.
- **Duplicate Detection**:
  - Automatically skips duplicate requests (same URL + method + body + status).
- **Request/Response Inspector**:
  - Browse captured requests with modern, light, clean arrow navigation (10-per-page pagination).
  - Detailed sub-tabs: Request details (headers/body), Response details (headers/body), and **Render Visual** to preview how the response looks inside a web browser.
- **Custom Request Sender / Inbuilt Browser (Postman Lite)**:
  - Create and execute custom calls on-the-fly.
  - Supports custom HTTP Methods (GET, POST, PUT, DELETE, PATCH, HEAD), editable request headers, bodies, and Auth credentials (NTLM, Basic Auth, Bearer Token).
  - **Right-Click Integration**: Send any selected request from the Capture or Replay tables straight to the Custom Request Sender via a neat right-click context menu.
- **Inbuilt Rendering Tab**:
  - Dedicated visual rendering frame that accepts direct URLs or Raw HTML code and renders them like in a browser.

---

## Installation & Dependencies

To install and run WebInvader, ensure you have Python 3.10+ installed and install the required libraries:

```bash
pip install requests requests-ntlm beautifulsoup4 tkinterweb pyinstaller playwright
playwright install chromium
```

---

## Usage Instructions

### Running the App
To start the GUI application:
```bash
python capture_replay.py
```

### Main Capture Dashboard
1. Enter your **Target Host** URL (e.g., `http://127.0.0.1:13845`).
2. Enter a **URL Pattern** to filter (e.g., `api/v2` or `*` to capture all traffic).
3. Select your **Capture Mode** (`Inbuilt Proxy (Port 8888)` or `Chrome CDP Browser`).
4. Click **CAPTURE** to start the listener thread.
5. Send request(s) using your application/browser. The captured calls will populate the paginated table below with color-coded status codes (green for 2xx, orange for 3xx, red for 4xx/5xx).
6. Export captured requests at any time using **📥 Export to CSV**.

### CSV Replay Tab
1. Switch to the **🔄 CSV REPLAY** tab.
2. Click **📁 UPLOAD CSV** and select your exported CSV file.
3. Choose your **Replay Auth** method (`No Auth`, `NTLM`, `Basic Auth`, `Bearer Token`) and enter the credentials.
4. Click **▶ Replay Selected** or **▶▶ Replay All** to replay live and view real-time responses!

### Custom Request Sender (Postman Lite)
1. Navigate to the **🚀 CUSTOM SENDER** tab.
2. Enter your Method, URL, Headers, and Body.
3. Choose your Authentication method.
4. Click **SEND REQUEST 🚀** to execute the call.
5. You can also right-click any captured request in the **Capture** or **Replay** tabs and select **Send to Custom API Sender** to instantly pre-populate all parameters!

---

## Testing & Verification

A comprehensive automated test suite and mock server are available inside the `tests/` directory:

### Running the Mock Server
Start the local mock server on port 13845 to test HTML rendering, mock JSON endpoints, and NTLM authentication:
```bash
python tests/mock_server.py
```

### Running Automated Unit Tests
To execute all test suites (including Domain & Pattern filtering, CSV Import/Export, and NTLM Auth Replay):
```bash
xvfb-run -a python -m unittest tests/test_capture_replay.py -v
```

---

## Compiling into a Standalone Executable

To compile `capture_replay.py` into a single standalone binary using PyInstaller:

```bash
pyinstaller --onefile capture_replay.py
```

The compiled binary will be generated under the `dist/` directory (e.g. `dist/capture_replay` or `dist/capture_replay.exe`).
