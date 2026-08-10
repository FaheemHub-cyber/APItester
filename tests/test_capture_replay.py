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
import capture_replay
from capture_replay import (
    WebInvaderApp,
    matches_filter,
    make_record_hash,
    build_traffic_record,
    ReplayEngine
)


class TestCaptureReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start mock server
        start_server()
        time.sleep(1)  # Allow port to bind

        # Mock messageboxes globally to avoid blocking
        capture_replay.messagebox.showinfo = lambda title, message, **kwargs: None
        capture_replay.messagebox.showerror = lambda title, message, **kwargs: None
        capture_replay.messagebox.showwarning = lambda title, message, **kwargs: None

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

        # Initialize targets
        self.app.targets = [{"host": f"http://127.0.0.1:{PORT}", "pattern": "*"}]
        self.app.active_targets = list(self.app.targets)

    def tearDown(self):
        self.app.stop_all_captures()
        try:
            self.app.destroy()
        except Exception:
            pass

    def test_matches_filter_wildcard_and_patterns(self):
        targets = [{"host": f"http://127.0.0.1:{PORT}", "pattern": "*"}]

        # Test wildcard match
        self.assertTrue(matches_filter(f"http://127.0.0.1:{PORT}/api/v2/items", targets))
        self.assertTrue(matches_filter(f"http://127.0.0.1:{PORT}/other-endpoint", targets))

    def test_multi_target_capture(self):
        # Setup multiple targets: one exact pattern and one other pattern
        self.app.targets = [
            {"host": f"http://127.0.0.1:{PORT}", "pattern": "api/v2"},
            {"host": f"http://127.0.0.1:{PORT}", "pattern": "other-endpoint"}
        ]
        self.app.active_targets = list(self.app.targets)

        # 1. Matches "api/v2" -> True
        self.app.check_and_capture(
            method="GET",
            url=f"http://127.0.0.1:{PORT}/api/v2/items",
            req_headers="X-Header: Value",
            req_body=b"",
            status_code=200,
            resp_headers={},
            resp_body=b'{"items": []}'
        )
        self.assertEqual(self.app.capture_queue.qsize(), 1)
        self.app.process_capture_queue()

        # 2. Matches "other-endpoint" -> True
        self.app.check_and_capture(
            method="GET",
            url=f"http://127.0.0.1:{PORT}/other-endpoint",
            req_headers="X-Header: Value",
            req_body=b"",
            status_code=200,
            resp_headers={},
            resp_body=b"other"
        )
        self.assertEqual(self.app.capture_queue.qsize(), 1)
        self.app.process_capture_queue()

        # 3. Matches neither -> False
        self.app.check_and_capture(
            method="GET",
            url=f"http://127.0.0.1:{PORT}/not-matching",
            req_headers="X-Header: Value",
            req_body=b"",
            status_code=200,
            resp_headers={},
            resp_body=b"none"
        )
        self.assertEqual(self.app.capture_queue.qsize(), 0)
        self.assertEqual(len(self.app.captured_requests), 2)

    def test_header_comments_parsing(self):
        raw_headers = """
        Content-Type: application/json
        //X-Disabled-Header: HiddenValue
        X-Enabled-Header: ActiveValue
        // Comment with no colon
        """
        parsed = ReplayEngine.parse_headers(raw_headers)

        self.assertIn("Content-Type", parsed)
        self.assertEqual(parsed["Content-Type"], "application/json")
        self.assertIn("X-Enabled-Header", parsed)
        self.assertEqual(parsed["X-Enabled-Header"], "ActiveValue")

        # Commented lines must NOT be in the parsed dict
        self.assertNotIn("X-Disabled-Header", parsed)
        self.assertNotIn("//X-Disabled-Header", parsed)

    def test_domain_and_pattern_filtering_and_capture(self):
        # Test exact host with wildcard pattern (*)
        self.app.check_and_capture(
            method="GET",
            url=f"http://127.0.0.1:{PORT}/api/v2/items",
            req_headers="Content-Type: application/json",
            req_body=b"",
            status_code=200,
            resp_headers={},
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
            req_headers="Content-Type: application/json",
            req_body=b"",
            status_code=200,
            resp_headers={},
            resp_body=b'{"items": []}'
        )
        self.assertEqual(self.app.capture_queue.qsize(), 0)  # Queued count stays 0 due to skip

    @patch("capture_replay.HttpNtlmAuth", side_effect=HTTPBasicAuth, create=True)
    def test_ntlm_authentication_replay(self, mock_ntlm):
        url = f"http://127.0.0.1:{PORT}/ntlm-auth"

        resp = ReplayEngine.execute(
            method="GET",
            url=url,
            headers="Content-Type: application/json",
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

            # Mock filedialog.askopenfilename directly on the capture_replay module
            original_ask = capture_replay.filedialog.askopenfilename
            capture_replay.filedialog.askopenfilename = lambda **kwargs: temp_csv

            # Execute CSV Import via CSVReplayFrame
            self.app.csv_replay_frame.upload_csv()

            # Restore
            capture_replay.filedialog.askopenfilename = original_ask

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
