import unittest
import os
import json
import csv
import time
import requests
import sys
from unittest.mock import patch
from requests.auth import HTTPBasicAuth

# Add root folder to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.mock_server import start_server, stop_server, PORT
import webinvader
from webinvader import WebInvaderApp


class TestWebInvader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start mock server
        start_server()
        time.sleep(1)  # Allow port to bind

        # Mock messageboxes globally to avoid blocking
        webinvader.messagebox.showinfo = lambda title, message, **kwargs: None
        webinvader.messagebox.showerror = lambda title, message, **kwargs: None
        webinvader.messagebox.showwarning = lambda title, message, **kwargs: None

    @classmethod
    def tearDownClass(cls):
        # Stop mock server
        stop_server()

    def setUp(self):
        # Create an instance of the WebInvader App
        self.app = WebInvaderApp()
        self.app.target_host_entry.delete(0, "end")
        self.app.target_host_entry.insert(0, f"http://127.0.0.1:{PORT}")
        self.app.pattern_entry.delete(0, "end")
        self.app.pattern_entry.insert(0, "*")

    def tearDown(self):
        self.app.stop_all_captures()
        try:
            self.app.destroy()
        except Exception:
            pass

    def test_domain_and_pattern_filtering_and_capture(self):
        # Test exact host with wildcard pattern (*)
        self.app.check_and_capture(
            method="GET",
            url=f"http://127.0.0.1:{PORT}/api/v2/items",
            req_headers={"Content-Type": "application/json"},
            req_body=b"",
            status_code=200,
            resp_headers={"Content-Type": "application/json"},
            resp_body=b'{"items": []}'
        )
        self.assertEqual(self.app.capture_queue.qsize(), 1)

        # Pull from queue to apply to captured_requests
        self.app.process_capture_queue()
        self.assertEqual(len(self.app.captured_requests), 1)
        self.assertEqual(self.app.captured_requests[0]["method"], "GET")
        self.assertEqual(self.app.captured_requests[0]["url"], f"http://127.0.0.1:{PORT}/api/v2/items")

        # Test duplicate detection: Same request should not be captured twice
        self.app.check_and_capture(
            method="GET",
            url=f"http://127.0.0.1:{PORT}/api/v2/items",
            req_headers={"Content-Type": "application/json"},
            req_body=b"",
            status_code=200,
            resp_headers={"Content-Type": "application/json"},
            resp_body=b'{"items": []}'
        )
        self.assertEqual(self.app.capture_queue.qsize(), 0)  # Queued count stays 0 due to skip

        # Test specific pattern matching (e.g. pattern = "api/v2")
        self.app.pattern_entry.delete(0, "end")
        self.app.pattern_entry.insert(0, "api/v2")

        # This matches pattern api/v2
        self.app.check_and_capture(
            method="POST",
            url=f"http://127.0.0.1:{PORT}/api/v2/items",
            req_headers={"Content-Type": "application/json"},
            req_body=b"payload",
            status_code=200,
            resp_headers={"Content-Type": "application/json"},
            resp_body=b'{"success": true}'
        )
        self.app.process_capture_queue()
        self.assertEqual(len(self.app.captured_requests), 2)

        # This does NOT match pattern api/v2 (should be skipped)
        self.app.check_and_capture(
            method="GET",
            url=f"http://127.0.0.1:{PORT}/other-endpoint",
            req_headers={"Content-Type": "text/plain"},
            req_body=b"",
            status_code=200,
            resp_headers={"Content-Type": "text/plain"},
            resp_body=b"other"
        )
        self.app.process_capture_queue()
        self.assertEqual(len(self.app.captured_requests), 2)  # Stays 2

    @patch("webinvader.HttpNtlmAuth", side_effect=HTTPBasicAuth, create=True)
    def test_ntlm_authentication_replay(self, mock_ntlm):
        url = f"http://127.0.0.1:{PORT}/ntlm-auth"

        resp = self.app.run_http_request(
            method="GET",
            url=url,
            headers='{"Content-Type": "application/json"}',
            body="",
            auth_type="NTLM",
            username="testuser",
            password="testpassword"
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(resp_data.get("status"), "authenticated")
        self.assertEqual(resp_data.get("auth"), "ntlm")

    def test_csv_export_and_import(self):
        # Populate captured requests
        item1 = {
            "id": 1,
            "method": "POST",
            "url": f"http://127.0.0.1:{PORT}/api/v2/items",
            "request_headers": {"Content-Type": "application/json", "X-Test": "Value1"},
            "request_body": b'{"name": "CSVItem"}',
            "status_code": 200,
            "response_headers": {"Content-Type": "application/json"},
            "response_body": b'{"status": "created"}'
        }
        self.app.captured_requests.append(item1)

        temp_csv = "temp_capture_test.csv"
        try:
            # Export to CSV
            self.app.write_csv_file(temp_csv, self.app.captured_requests)
            self.assertTrue(os.path.exists(temp_csv))

            # Mock filedialog.askopenfilename directly on the webinvader module
            original_ask = webinvader.filedialog.askopenfilename
            webinvader.filedialog.askopenfilename = lambda **kwargs: temp_csv

            # Execute CSV Import
            self.app.upload_csv()

            # Restore
            webinvader.filedialog.askopenfilename = original_ask

            # Check if imported successfully
            self.assertEqual(len(self.app.replay_requests), 1)
            imported_item = self.app.replay_requests[0]
            self.assertEqual(imported_item["method"], "POST")
            self.assertEqual(imported_item["url"], f"http://127.0.0.1:{PORT}/api/v2/items")
            self.assertEqual(imported_item["request_headers"].get("X-Test"), "Value1")
            self.assertEqual(imported_item["request_body"], b'{"name": "CSVItem"}')

        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)


if __name__ == "__main__":
    unittest.main()
