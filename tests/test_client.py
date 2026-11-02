"""Local transport and credential boundaries; never contact a model provider."""
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch
from urllib import error

from harness_lab.client import BudgetExceeded, LocalClient, ModelError, load_key, local_base_url


class MockResponse(io.BytesIO):
    def __init__(self, content, headers=None):
        super().__init__(content)
        self.headers = headers or {}


def completion(content='{"ok":true}', finish_reason="stop", **extra):
    return json.dumps({
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        **extra,
    }).encode("utf-8")


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run_dir = Path(self.temp.name)
        self.secret = "freellmapi-test-secret-never-in-traces"
        self.env = patch.dict(os.environ, {"HARNESS_CLIENT_TEST_KEY": self.secret})
        self.env.start()
        self.addCleanup(self.env.stop)

    def client(self, **overrides):
        config = {
            "base_url": "http://127.0.0.1:3002/v1",
            "model": "test-model",
            "api_key_env": "HARNESS_CLIENT_TEST_KEY",
            "transport_retries": 1,
            "max_requests": 4,
            "min_interval_seconds": 0,
        }
        config.update(overrides)
        return LocalClient(config, self.run_dir)

    def mock_transport(self, client, *outcomes):
        # Preserve urllib's context-manager, read, and response-header interfaces.
        opener = Mock()
        opener.open.side_effect = [
            MockResponse(value) if isinstance(value, bytes) else value
            for value in outcomes
        ]
        client._opener = opener
        return opener

    def records(self):
        return [json.loads(line) for line in (self.run_dir / "trace.jsonl").read_text().splitlines()]

    def test_503_retry_consumes_request_budget_and_succeeds(self):
        client = self.client(max_requests=2)
        opener = self.mock_transport(
            client,
            error.HTTPError(client.base_url, 503, "unavailable", {}, io.BytesIO(b"private body")),
            completion(usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}),
        )
        with patch("harness_lab.client.time.sleep"):
            result = client.complete([{"role": "user", "content": "test"}], role="worker")
        self.assertEqual(result["text"], '{"ok":true}')
        self.assertEqual(client.attempts, 2)
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(client.usage["total_tokens"], 7)
        self.assertEqual([item["event"] for item in self.records()],
                         ["request", "error", "retry_wait", "request", "response"])
        with self.assertRaises(BudgetExceeded):
            client.complete([], role="worker")
        self.assertEqual(opener.open.call_count, 2)

    def test_retry_cannot_cross_request_budget(self):
        client = self.client(max_requests=1, transport_retries=3)
        opener = self.mock_transport(
            client, error.HTTPError(client.base_url, 503, "unavailable", {}, io.BytesIO()),
        )
        with patch("harness_lab.client.time.sleep"), self.assertRaises(BudgetExceeded):
            client.complete([], role="worker")
        self.assertEqual(client.attempts, 1)
        self.assertEqual(opener.open.call_count, 1)

    def test_auth_failure_is_not_retried_or_disclosed(self):
        client = self.client(transport_retries=3)
        private_body = "private upstream error body " + self.secret
        body = io.BytesIO(private_body.encode())
        opener = self.mock_transport(
            client, error.HTTPError(client.base_url, 401, self.secret, {}, body),
        )
        with self.assertRaisesRegex(ModelError, "HTTP 401") as caught:
            client.complete([], role="worker")
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(body.tell(), 0)
        trace = (self.run_dir / "trace.jsonl").read_text()
        for protected in (self.secret, private_body):
            self.assertNotIn(protected, trace)
            self.assertNotIn(protected, str(caught.exception))

    def test_retry_after_seconds_are_honored_including_sixty_second_boundary(self):
        for seconds in (12, 60):
            with self.subTest(seconds=seconds):
                client = self.client(max_requests=2)
                opener = self.mock_transport(
                    client,
                    error.HTTPError(client.base_url, 429, "rate limited", {"Retry-After": str(seconds)}, io.BytesIO()),
                    completion(),
                )
                with patch("harness_lab.client.time.sleep") as sleep:
                    client.complete([], role="worker")
                sleep.assert_called_once_with(float(seconds))
                self.assertEqual(opener.open.call_count, 2)
                self.assertEqual(client.attempts, 2)

    def test_long_retry_after_stops_without_early_retry(self):
        client = self.client(transport_retries=3)
        opener = self.mock_transport(
            client,
            error.HTTPError(client.base_url, 429, "rate limited", {"Retry-After": "61"}, io.BytesIO()),
        )
        with patch("harness_lab.client.time.sleep") as sleep, self.assertRaisesRegex(ModelError, "retry later"):
            client.complete([], role="worker")
        sleep.assert_not_called()
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(client.attempts, 1)

    def test_pacing_waits_only_remaining_interval_between_requests(self):
        client = self.client(min_interval_seconds=60)
        self.mock_transport(client, completion(), completion(), completion())
        clock = [100.0]

        def advance(seconds):
            clock[0] += seconds

        with patch("harness_lab.client.time.monotonic", side_effect=lambda: clock[0]), \
                patch("harness_lab.client.time.sleep", side_effect=advance) as sleep:
            client.complete([], role="first")
            sleep.assert_not_called()
            clock[0] += 10
            client.complete([], role="second")
            sleep.assert_called_once_with(50.0)
            clock[0] += 75
            client.complete([], role="third")
            sleep.assert_called_once_with(50.0)
        self.assertEqual(client.attempts, 3)

    def test_pacing_accounts_for_time_already_spent_in_retry_after(self):
        client = self.client(min_interval_seconds=60, max_requests=2)
        self.mock_transport(
            client,
            error.HTTPError(client.base_url, 429, "rate limited", {"Retry-After": "12"}, io.BytesIO()),
            completion(),
        )
        clock = [100.0]

        def advance(seconds):
            clock[0] += seconds

        with patch("harness_lab.client.time.monotonic", side_effect=lambda: clock[0]), \
                patch("harness_lab.client.time.sleep", side_effect=advance) as sleep:
            client.complete([], role="worker")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [12.0, 48.0])
        self.assertEqual(clock[0], 160.0)
        self.assertEqual(client.attempts, 2)

    def test_redirect_is_rejected_without_following_location(self):
        hits = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append(self.path)
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.send_response(302)
                self.send_header("Location", "/redirect-target")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(completion())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = self.client(base_url="http://127.0.0.1:%s/v1" % server.server_port)
            with self.assertRaisesRegex(ModelError, "HTTP 302"):
                client.complete([], role="worker")
            self.assertEqual(hits, ["/v1/chat/completions"])
            self.assertEqual(client.attempts, 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_malformed_chat_payloads_raise_model_error_without_retry(self):
        for raw in (b"not json", b"[]", b"{}", b'{"choices":[]}',
                    b'{"choices":[{"message":{"content":null}}]}'):
            with self.subTest(raw=raw):
                client = self.client()
                opener = self.mock_transport(client, raw)
                with self.assertRaises(ModelError):
                    client.complete([], role="worker")
                self.assertEqual(opener.open.call_count, 1)

    def test_truncated_output_is_not_treated_as_success(self):
        client = self.client()
        self.mock_transport(client, completion('{"unfinished":', finish_reason="length",
                                               usage={"prompt_tokens": 15, "completion_tokens": 64,
                                                      "total_tokens": 79}))
        with self.assertRaisesRegex(ModelError, "truncated"):
            client.complete([], role="worker")
        self.assertNotIn("response", [record["event"] for record in self.records()])
        self.assertTrue(client.usage_available)
        self.assertEqual(client.usage, {"prompt_tokens": 15, "completion_tokens": 64, "total_tokens": 79})

    def test_oversized_response_is_rejected(self):
        client = self.client()
        self.mock_transport(client, b"x" * 2_000_001)
        with self.assertRaisesRegex(ModelError, "exceeds 2 MB"):
            client.complete([], role="worker")

    def test_oversized_request_does_not_spend_budget(self):
        client = self.client()
        opener = self.mock_transport(client)
        with self.assertRaisesRegex(ModelError, "context payload limit"):
            client.complete([{"role": "user", "content": "x" * 200_001}], role="worker")
        self.assertEqual(client.attempts, 0)
        opener.open.assert_not_called()

    def test_credentials_are_redacted_from_request_response_and_returned_text(self):
        client = self.client()
        opener = self.mock_transport(client, completion("echo " + self.secret))
        result = client.complete([{"role": "user", "content": self.secret}], role="worker")
        self.assertEqual(result["text"], "echo [REDACTED]")
        trace = (self.run_dir / "trace.jsonl").read_text()
        self.assertNotIn(self.secret, trace)
        self.assertIn("[REDACTED]", trace)
        sent_request = opener.open.call_args.args[0]
        self.assertEqual(sent_request.get_header("Authorization"), "Bearer " + self.secret)

    def test_model_discovery_checks_shape(self):
        client = self.client()
        self.mock_transport(client, json.dumps({"data": [{"id": "good"}, {}, {"id": 123}]}).encode())
        self.assertEqual(client.models(), ["good"])
        self.mock_transport(client, b'{"data":"bad"}')
        with self.assertRaises(ModelError):
            client.models()

    def test_response_records_actual_model_and_provider(self):
        client = self.client()
        response = MockResponse(completion(model="resolved-model"), {"X-Routed-Via": "provider/resolved-model"})
        self.mock_transport(client, response)
        client.complete([], role="worker")
        self.assertEqual(client.resolved_models, {"resolved-model"})
        record = self.records()[-1]
        self.assertEqual(record["resolved_model"], "resolved-model")
        self.assertEqual(record["routed_via"], "provider/resolved-model")


class ConfigTests(unittest.TestCase):
    def test_sqlite_key_is_read_only_and_connection_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "existing-router.db"
            connection = sqlite3.connect(str(database))
            connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO settings VALUES (?, ?)", ("unified_api_key", " existing-key "))
            connection.commit()
            connection.close()
            before = database.read_bytes()
            actual_connect = sqlite3.connect
            observed = []

            def track_connection(database_uri, **kwargs):
                self.assertIn("mode=ro", database_uri)
                self.assertTrue(kwargs.get("uri"))
                result = actual_connect(database_uri, **kwargs)
                observed.append(result)
                # Check the actual connection, not merely its URI spelling.
                with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                    result.execute("UPDATE settings SET value='must not be writable'")
                return result

            try:
                with patch.dict(os.environ, {"HARNESS_CLIENT_TEST_SOURCE": ""}), \
                        patch("harness_lab.client.sqlite3.connect", side_effect=track_connection):
                    self.assertEqual(load_key({"api_key_env": "HARNESS_CLIENT_TEST_SOURCE",
                                               "api_key_sqlite_path": str(database)}), "existing-key")
                self.assertEqual(database.read_bytes(), before)
                self.assertEqual(len(observed), 1)
                with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed"):
                    observed[0].execute("SELECT 1")
            finally:
                for connection in observed:
                    connection.close()

    def test_missing_sqlite_source_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "missing.db"
            with patch.dict(os.environ, {"HARNESS_CLIENT_TEST_SOURCE": ""}), \
                    self.assertRaises((ValueError, sqlite3.Error)):
                load_key({"api_key_env": "HARNESS_CLIENT_TEST_SOURCE", "api_key_sqlite_path": str(database)})
            self.assertFalse(database.exists())

    def test_allows_loopback_urls(self):
        for url in ("http://localhost:3002/v1", "http://127.0.0.1:3002/v1/",
                    "http://127.7.8.9/v1", "http://[::1]:3002/v1"):
            with self.subTest(url=url):
                self.assertEqual(local_base_url(url), url.rstrip("/"))

    def test_rejects_remote_and_ambiguous_urls(self):
        for url in (
            "http://example.com/v1", "http://192.168.1.2/v1", "http://0.0.0.0/v1",
            "http://localhost.example.com/v1", "https://localhost/v1",
            "http://user:password@localhost/v1", "http://localhost/v1?key=secret",
            "http://localhost/v1#fragment", "http://localhost/other",
            "http://localhost:99999/v1", "file:///v1",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_base_url(url)

    def test_env_key_precedes_file_and_nested_json_file_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key.json"
            path.write_text(json.dumps({"connection": {"key": " file-key "}}))
            config = {"api_key_env": "HARNESS_CLIENT_TEST_SOURCE", "api_key_file": str(path),
                      "api_key_field": "connection.key"}
            with patch.dict(os.environ, {"HARNESS_CLIENT_TEST_SOURCE": "env-key"}):
                self.assertEqual(load_key(config), "env-key")
            with patch.dict(os.environ, {"HARNESS_CLIENT_TEST_SOURCE": ""}):
                self.assertEqual(load_key(config), "file-key")

    def test_nonstring_credential_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key.json"
            path.write_text('{"key":123}')
            with patch.dict(os.environ, {"HARNESS_CLIENT_TEST_SOURCE": ""}), self.assertRaises(ValueError):
                load_key({"api_key_env": "HARNESS_CLIENT_TEST_SOURCE", "api_key_file": str(path),
                          "api_key_field": "key"})


if __name__ == "__main__":
    unittest.main()
