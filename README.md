# WebInvader — API Traffic Capturer v0.3

A lightweight Python GUI application for HTTP traffic capture & replay supporting Chrome DevTools Protocol (CDP), CSV Upload & Replay, an Inbuilt Browser/API Requester, and an Inbuilt Proxy Interceptor.

## Features

- **Dedicated CSV Replay Tab**:
  - Upload exported CSV files (`webinvader_capture.csv` or standard HTTP request CSVs).
  - Inspect all loaded request/response records in dark-themed paginated table UI.
  - Replay individual requests (**Replay Selected**) or bulk-replay all requests (**Replay All**) manually with configurable Auth (No Auth, NTLM, Basic Auth, Bearer Token).
- **Multiple Capture Modes**:
  - **Chrome CDP Browser** — Launches Chrome with `--remote-allow-origins=*` remote debugging and monitors network traffic in real-time.
  - **Inbuilt Browser & API Requester** — Native in-app browser & HTTP API requester for navigating and sending GET/POST/PUT/DELETE calls directly without Chrome.
  - **Inbuilt Proxy Server (Port 8888)** — Built-in HTTP proxy interceptor to capture traffic from any external browser or application.
- **Pattern & Host Filtering** — Captures requests matching your target host (e.g. `http://localhost:13845`) and URL pattern (e.g. `api/v2`).
- **Duplicate Detection** — Automatically skips duplicate requests (same URL + method + body + status).
- **Paginated Table** — Browse captured requests 5-per-page with arrow navigation.
- **Color-Coded Status** — Green for success (2xx), red for errors (4xx/5xx), orange for redirects (3xx).
- **Request/Response Inspector** — View headers, body, and query parameters in tabbed detail view.
- **CSV Export** — Export all captured traffic to a spreadsheet.
- **Pre-configured Auth** — NTLM, Basic Auth, and Bearer Token credentials stored in `config.json`.
- **Dark Theme** — Modern, professional dark UI.

## Usage

```bash
python capture_replay.py
```

### Main Capture Dashboard
1. Enter your **Target Host** URL (e.g., `http://localhost:13845`)
2. Enter a **URL Pattern** to filter (e.g., `api/v2`)
3. Select your **Mode** (`Chrome CDP Browser`, `Inbuilt Browser / API Requester`, `Inbuilt Proxy (Port 8888)`)
4. Click **CAPTURE**
5. Export captured requests using **Export to CSV**.

### CSV Replay Tab
1. Switch to the **🔄 CSV Replay** tab.
2. Click **📁 UPLOAD CSV** and select your exported CSV file.
3. Choose your **Replay Auth** method (`No Auth`, `NTLM`, `Basic Auth`, `Bearer Token`).
4. Click **▶ Replay Selected** or **▶▶ Replay All** to send requests live and receive real-time status & responses!

## Dependencies

- `websocket-client`
- `requests`
- `requests-ntlm`
