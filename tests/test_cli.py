"""Evaluation orchestration tests; fake clients never open network connections."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from harness_lab import __main__ as cli


def result_fixture(findings=None, completed=True, status=None):
    findings = [] if findings is None else findings
    if status is None:
        status = "needs_attention" if findings else "ready_for_human_review"
    return {"status": status, "completed": completed, "outstanding_findings": findings}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="harness-evaluation-test-")
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "evaluation"
        self.output.mkdir()
        self.dataset = cli.load_json(cli.ROOT / "examples/evaluation.json")
        self.config = {
            "base_url": "http://127.0.0.1:12345/v1",
            "model": "offline-test-client",
            "min_interval_seconds": 60,
        }

    def evaluate(self, results, case=None, trials=1):
        args = SimpleNamespace(output=str(self.output.parent), case=case, trials=trials)
        clients = []
        dispatches = []
        pending = iter(results)

        def make_client(config, path, *, last_dispatch=None):
            client = SimpleNamespace(
                mode="live", attempts=2, usage={}, usage_available=False,
                resolved_models=set(), last_dispatch=last_dispatch,
            )
            clients.append(client)
            return client

        def fake_run(task, client, path, **kwargs):
            # An actual run updates this after its final HTTP dispatch. Advance a
            # deterministic marker to check the handoff without sleeping.
            client.last_dispatch = 100.0 + len(dispatches) * 60.0
            dispatches.append(client.last_dispatch)
            return copy.deepcopy(next(pending))

        with patch.object(cli, "LocalClient", side_effect=make_client) as client_mock, \
                patch.object(cli, "run", side_effect=fake_run) as run_mock, \
                patch.object(cli, "new_run", return_value=self.output) as new_run_mock, \
                redirect_stdout(io.StringIO()):
            exit_code = cli.evaluation(args, self.config)
        new_run_mock.assert_called_once_with(args.output, "evaluation")
        saved = json.loads((self.output / "evaluation.json").read_text(encoding="utf-8"))
        return exit_code, saved, client_mock, run_mock, clients, dispatches

    def test_expected_labels_stay_outside_runtime_inputs(self):
        results = []
        for case in self.dataset:
            findings = [dict(expected, severity="major") for expected in case["expected"]]
            results.append(result_fixture(findings))
        exit_code, saved, _, run_mock, clients, _ = self.evaluate(results)
        self.assertEqual(exit_code, 0)
        self.assertEqual(run_mock.call_count, len(self.dataset))
        for index, (case, call) in enumerate(zip(self.dataset, run_mock.call_args_list)):
            self.assertEqual(call.args, (
                case["task"], clients[index], self.output / (case["id"] + "-trial-1"),
            ))
            self.assertEqual(call.kwargs, {"max_revisions": 0, "initial_draft": case["draft"]})
            self.assertNotIn("expected", call.args[0])
            self.assertNotIn("id", call.args[0])
            self.assertEqual(saved["rows"][index]["detected"], len(case["expected"]))

    def test_last_dispatch_is_carried_across_trials_and_cases(self):
        total_runs = len(self.dataset) * 2
        exit_code, saved, client_mock, _, _, dispatches = self.evaluate(
            [result_fixture() for _ in range(total_runs)], trials=2,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(client_mock.call_count, total_runs)
        received = [call.kwargs["last_dispatch"] for call in client_mock.call_args_list]
        self.assertEqual(received, [None] + dispatches[:-1])
        self.assertEqual(
            [(row["case"], row["trial"]) for row in saved["rows"]],
            [(case["id"], trial) for case in self.dataset for trial in (1, 2)],
        )

    def test_failed_case_has_unknown_detection_even_when_partial_findings_match(self):
        case = next(item for item in self.dataset if item["expected"])
        partial = [dict(expected, severity="major") for expected in case["expected"]]
        exit_code, saved, _, _, _, _ = self.evaluate([
            result_fixture(partial, completed=False, status="failed"),
        ], case=case["id"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(len(saved["rows"]), 1)
        row = saved["rows"][0]
        self.assertFalse(row["completed"])
        self.assertEqual(row["status"], "failed")
        self.assertIsNone(row["detected"])
        self.assertEqual(row["major_findings"], len(partial))

    def test_clean_case_with_no_findings_reports_zero_without_dividing_by_zero(self):
        clean = next(item for item in self.dataset if not item["expected"])
        exit_code, saved, _, run_mock, _, _ = self.evaluate([result_fixture()], case=clean["id"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(run_mock.call_count, 1)
        row = saved["rows"][0]
        self.assertTrue(row["completed"])
        self.assertEqual(row["status"], "ready_for_human_review")
        self.assertEqual(row["expected"], 0)
        self.assertEqual(row["detected"], 0)
        self.assertEqual(row["major_findings"], 0)


if __name__ == "__main__":
    unittest.main()
