import json
import os
import tempfile
import threading
import unittest
from http.server import HTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from app.app import Handler, read_secret_status


class VaultDemoAppTests(unittest.TestCase):
    def test_secret_file_detects_both_fields(self):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False
        ) as file:
            file.write("Username: test-user\nPassword: fake-password\n")
            path = file.name

        try:
            with patch("app.app.SECRET_FILE", path):
                result = read_secret_status()

            self.assertTrue(result["secret_file_found"])
            self.assertTrue(result["username_present"])
            self.assertTrue(result["password_present"])
        finally:
            os.unlink(path)

    def test_missing_secret_file(self):
        with patch("app.app.SECRET_FILE", "/nonexistent/test-secret-file"):
            result = read_secret_status()

        self.assertFalse(result["secret_file_found"])
        self.assertFalse(result["username_present"])
        self.assertFalse(result["password_present"])

    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_health_endpoint(self):
        with urlopen(f"{self.base_url}/health") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(
                json.loads(response.read()),
                {"status": "ok"},
            )

    def test_db_check_endpoint_success(self):
        expected = {
            "database": "connected",
            "query_successful": True,
            "sample_row": "Vault dynamic credentials test",
        }

        with patch("app.app.check_database", return_value=(200, expected)):
            with urlopen(f"{self.base_url}/db-check") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read()), expected)

    def test_db_check_endpoint_failure(self):
        expected = {
            "database": "error",
            "query_successful": False,
            "message": "Database check failed",
        }

        with patch("app.app.check_database", return_value=(503, expected)):
            with self.assertRaises(HTTPError) as error:
                urlopen(f"{self.base_url}/db-check")

        self.assertEqual(error.exception.code, 503)
        self.assertEqual(json.loads(error.exception.read()), expected)

    def test_status_endpoint_does_not_expose_secret_values(self):
        fake_username = "fake-user-for-test"
        fake_password = "fake-password-for-test"

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False
        ) as file:
            file.write(f"Username: {fake_username}\\nPassword: {fake_password}\\n")
            secret_path = file.name

        try:
            with patch("app.app.SECRET_FILE", secret_path):
                with urlopen(f"{self.base_url}/status") as response:
                    body = response.read().decode("utf-8")
                    result = json.loads(body)

            self.assertTrue(result["secret_file_found"])
            self.assertNotIn(fake_username, body)
            self.assertNotIn(fake_password, body)
        finally:
            os.unlink(secret_path)

    def test_db_check_failure_does_not_expose_credentials(self):
        fake_username = "fake-db-user-for-test"
        fake_password = "fake-db-password-for-test"

        failure = (
            503,
            {
                "database": "error",
                "query_successful": False,
                "message": "Database check failed",
            },
        )

        with patch("app.app.check_database", return_value=failure):
            with self.assertRaises(HTTPError) as error:
                urlopen(f"{self.base_url}/db-check")

        body = error.exception.read().decode("utf-8")
        self.assertEqual(error.exception.code, 503)
        self.assertNotIn(fake_username, body)
        self.assertNotIn(fake_password, body)
        self.assertNotIn("password", body.lower())

    def test_unknown_endpoint_returns_generic_error(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(f"{self.base_url}/internal-debug-details")

        body = error.exception.read().decode("utf-8")
        self.assertEqual(error.exception.code, 404)
        self.assertEqual(json.loads(body), {"error": "not found"})
        self.assertNotIn("Traceback", body)
        self.assertNotIn("password", body.lower())

    def test_unknown_endpoint_returns_404(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(f"{self.base_url}/not-found")

        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
