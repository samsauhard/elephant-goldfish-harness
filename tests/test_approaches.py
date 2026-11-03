"""Exercise the three CLI paths through a fake HTTP transport, never a provider."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from harness_lab import __main__ as cli
from harness_lab.client import LocalClient
from harness_lab.direct import direct_config, run_direct


class Response(io.BytesIO):
    headers = {}


def completion(text):
    return Response(json.dumps({"model": "test-model", "choices": [
        {"finish_reason": "stop", "message": {"content": text}}],
        "usage": {"total_tokens": 12}}).encode("utf-8"))


class ApproachTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = {"base_url": "http://127.0.0.1:12345/v1", "model": "test-model",
                       "max_requests": 12, "transport_retries": 2, "json_mode": True,
                       "min_interval_seconds": 0}
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.task = cli.load_json(cli.ROOT / "examples/review-task.json")
        self.task["planning_notes"] = "AUTHOR_ONLY_SENTINEL"
        self.task_path = self.root / "task.json"
        self.task_path.write_text(json.dumps(self.task), encoding="utf-8")
        self.draft_path = cli.ROOT / "examples/review-draft.json"

    def invoke(self, approach, responses, draft=None):
        clients = []

        def make_client(config, output):
            with patch("harness_lab.client.load_key", return_value="test-secret"):
                client = LocalClient(config, output)
            client._opener = Mock()
            client._opener.open.side_effect = responses
            clients.append(client)
            return client

        with patch.object(cli, "LocalClient", side_effect=make_client), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = cli.main(["review", "--approach", approach, "--config", str(self.config_path),
                             "--task", str(self.task_path), "--draft", str(draft or self.draft_path),
                             "--model", "explicit-test-model", "--output", str(self.root / "runs")])
        if not clients:
            return code, None, None, None
        client = clients[0]
        result = json.loads((client.run_dir / "result.json").read_text(encoding="utf-8"))
        metadata = json.loads((client.run_dir / "metadata.json").read_text(encoding="utf-8"))
        return code, client, result, metadata

    def test_direct_keeps_unvalidated_text_and_makes_exactly_one_request(self):
        text = 'This is not JSON. A claimed quote may be invented. test-secret'
        code, client, result, metadata = self.invoke("direct", [completion(text)])
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "response_received_unvalidated")
        self.assertFalse(result["output_validated"])
        self.assertNotIn("outstanding_findings", result)
        self.assertEqual(client._opener.open.call_count, 1)
        self.assertEqual((client.max_requests, client.retries, client.json_mode), (1, 0, False))
        self.assertEqual((client.run_dir / "response.txt").read_text(encoding="utf-8"),
                         text.replace("test-secret", "[REDACTED]"))
        payload = json.loads(client._opener.open.call_args.args[0].data)
        self.assertNotIn("response_format", payload)
        self.assertEqual(payload["model"], "explicit-test-model")
        self.assertEqual([m["role"] for m in payload["messages"]], ["system", "user"])
        self.assertNotIn("AUTHOR_ONLY_SENTINEL", json.dumps(payload))
        self.assertEqual(set(json.loads(payload["messages"][1]["content"])), {"draft", "references"})
        self.assertEqual(metadata["configuration"]["approach"], "direct")
        self.assertEqual(metadata["attempts"], 1)

    def test_direct_503_is_not_retried_and_failure_artifacts_remain(self):
        failure = HTTPError("http://127.0.0.1:12345/v1", 503, "test-secret", {}, io.BytesIO())
        code, client, result, _ = self.invoke("direct", [failure])
        self.assertEqual(code, 1)
        self.assertFalse(result["completed"])
        self.assertEqual(client._opener.open.call_count, 1)
        self.assertEqual(result["correction_attempts"], 0)
        self.assertFalse((client.run_dir / "response.txt").exists())
        self.assertNotIn("test-secret", json.dumps(result))

    def test_both_egm_paths_use_two_fresh_reviews_without_author_generation(self):
        empty = json.dumps({"summary": "Fixture only, not a model-quality result.", "findings": []})
        for approach in ("egm", "grounded"):
            with self.subTest(approach=approach):
                code, client, result, metadata = self.invoke(approach, [completion(empty), completion(empty)])
                self.assertEqual(code, 0)
                self.assertTrue(result["completed"])
                self.assertEqual(client._opener.open.call_count, 2)
                self.assertEqual(result["revisions_used"], 0)
                payloads = [json.loads(call.args[0].data) for call in client._opener.open.call_args_list]
                for payload in payloads:
                    self.assertEqual([m["role"] for m in payload["messages"]], ["system", "user"])
                    self.assertNotIn("AUTHOR_ONLY_SENTINEL", json.dumps(payload))
                self.assertEqual(payloads[0]["messages"][1], payloads[1]["messages"][1])
                self.assertNotEqual(payloads[0]["messages"][0], payloads[1]["messages"][0])
                self.assertEqual(metadata["configuration"]["review_mode"],
                                 "legacy" if approach == "egm" else "grounded")
                self.assertEqual((client.run_dir / "grounding-0.json").exists(), approach == "grounded")

    def test_egm_uses_bounded_correction_where_direct_accepts_the_text(self):
        empty = json.dumps({"summary": "Fixture only.", "findings": []})
        code, client, result, _ = self.invoke("egm", [completion("not JSON"), completion(empty), completion(empty)])
        self.assertEqual(code, 0)
        self.assertEqual(client.attempts, 3)
        self.assertEqual(result["correction_attempts"], 1)

    def test_invalid_input_cannot_dispatch_in_any_approach(self):
        broken = self.root / "broken.json"
        broken.write_text("{}", encoding="utf-8")
        for approach in ("direct", "egm", "grounded"):
            code, client, _, _ = self.invoke(approach, [], draft=broken)
            self.assertEqual(code, 1)
            self.assertIsNone(client)

    def test_direct_rejects_a_client_with_retry_capability_enabled(self):
        with patch("harness_lab.client.load_key", return_value=""):
            client = LocalClient(self.config)
        with self.assertRaises(ValueError):
            run_direct(self.task, cli.load_json(self.draft_path), client, self.root / "unsafe")
        self.assertEqual(client.attempts, 0)
        configured = direct_config(self.config)
        self.assertEqual(self.config["transport_retries"], 2)
        self.assertEqual(configured["transport_retries"], 0)


if __name__ == "__main__":
    unittest.main()
