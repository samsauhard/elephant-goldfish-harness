"""Offline workflow tests with independently scripted model responses."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from harness_lab.client import BudgetExceeded
from harness_lab.runtime import run


PRIVATE_NOTES = "AUTHOR_PRIVATE_49bca: prefer the easiest implementation"
FIRST_FINDING = "COMPREHENSION_ONLY_a3c9: repeated POST can duplicate jobs"
SECOND_FINDING = "CRITIC_ONLY_81ef: clarify retry acceptance criteria"


def task_fixture():
    return {
        "title": "Export API",
        "brief": "Design asynchronous export jobs.",
        "references": ["REFERENCE_01: Each tenant can only access its own exports."],
        "planning_notes": PRIVATE_NOTES,
    }


def draft_fixture(revised=False):
    return {
        "title": "Create export jobs",
        "problem": "Customers need an asynchronous export API.",
        "goals": ["Accept a bounded export request"],
        "design": (
            "POST /exports creates a tenant-scoped job. Idempotency keys replay the same job ID."
            if revised else "POST /exports creates a job. Clients retry failed requests."
        ),
        "alternatives": ["Synchronous exports would hold connections open."],
        "risks": ["Resource exhaustion requires per-tenant limits."],
        "acceptance_tests": ["A valid request returns HTTP 202 and a job ID."],
        "open_questions": [],
    }


def review_fixture(issue=None, severity="major"):
    findings = [] if issue is None else [{
        "severity": severity,
        "category": "reliability",
        "section": "design",
        "evidence": "Clients retry failed requests.",
        "issue": issue,
        "recommendation": "Define idempotent retries and verify duplicate requests.",
    }]
    return {"summary": "Independent inspection of the supplied draft.", "findings": findings}


class FakeClient:
    """Scripted text, optional failures, and an actual bounded call counter."""
    mode = "scripted"
    model = "unit-test-fixture"

    def __init__(self, responses, max_requests=100):
        self.responses = list(responses)
        self.max_requests = max_requests
        self.attempts = 0
        self.calls = []

    def complete(self, messages, *, role):
        if self.attempts >= self.max_requests:
            raise BudgetExceeded("HTTP request budget exhausted")
        self.attempts += 1
        self.calls.append({"role": role, "messages": copy.deepcopy(messages)})
        if not self.responses:
            raise AssertionError("Unexpected extra model request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return {
            "text": response if isinstance(response, str) else json.dumps(response),
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "latency_ms": 1.25,
        }


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="harness-runtime-test-")
        self.addCleanup(directory.cleanup)
        self.run_dir = Path(directory.name) / "run"

    def execute(self, responses, **options):
        client = FakeClient(responses, max_requests=options.pop("max_requests", 100))
        summary = run(task_fixture(), client, self.run_dir, **options)
        return summary, client

    def assert_saved_summary(self, summary):
        saved = json.loads((self.run_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, summary)
        report = (self.run_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn(summary["status"], report)
        self.assertIn("scripted", report.lower())

    def test_fresh_reviewers_receive_only_draft_and_explicit_references(self):
        summary, client = self.execute([
            draft_fixture(), review_fixture(FIRST_FINDING), review_fixture(SECOND_FINDING, "nit"),
            draft_fixture(revised=True), review_fixture(), review_fixture(),
        ])
        self.assertEqual(summary["status"], "ready_for_human_review")
        self.assertTrue(summary["completed"])
        self.assertEqual([call["role"] for call in client.calls], [
            "author", "comprehension", "design_critic", "revision", "comprehension", "design_critic",
        ])
        self.assertIn(PRIVATE_NOTES, json.dumps(client.calls[0]["messages"]))
        revision_text = json.dumps(client.calls[3]["messages"])
        for marker in (PRIVATE_NOTES, FIRST_FINDING, SECOND_FINDING):
            self.assertIn(marker, revision_text)
        for index in (1, 2, 4, 5):
            messages = client.calls[index]["messages"]
            self.assertEqual([message["role"] for message in messages], ["system", "user"])
            payload = json.loads(messages[1]["content"])
            self.assertEqual(set(payload), {"draft", "references"})
            self.assertEqual(payload["references"], task_fixture()["references"])
            self.assertEqual(payload["draft"], draft_fixture(revised=index >= 4))
            for marker in (PRIVATE_NOTES, FIRST_FINDING, SECOND_FINDING):
                self.assertNotIn(marker, json.dumps(messages))
        self.assertEqual(summary["revisions_used"], 1)
        self.assertEqual(len(summary["drafts"]), 2)
        self.assertEqual(len(summary["review_artifacts"]), 4)
        self.assertEqual(summary["final_design"], "design.md")
        design = (self.run_dir / "design.md").read_text(encoding="utf-8")
        self.assertIn(draft_fixture(revised=True)["design"], design)
        self.assertNotIn(draft_fixture()["design"], design)
        self.assertIn("## Acceptance tests", design)
        self.assertIn("(design.md)", (self.run_dir / "report.md").read_text(encoding="utf-8"))
        self.assert_saved_summary(summary)

    def test_zero_revisions_with_major_or_blocker_needs_attention(self):
        for severity in ("major", "blocker"):
            with self.subTest(severity=severity):
                summary, client = self.execute([
                    draft_fixture(), review_fixture(FIRST_FINDING, severity), review_fixture(),
                ], max_revisions=0)
                self.assertEqual(summary["status"], "needs_attention")
                self.assertTrue(summary["completed"])
                self.assertEqual(summary["remaining_major_findings"], 1)
                self.assertEqual(summary["revisions_used"], 0)
                self.assertEqual(len(client.calls), 3)
                self.assert_saved_summary(summary)

    def test_nits_allow_ready_only_after_both_valid_reviews(self):
        summary, client = self.execute([
            draft_fixture(), review_fixture(FIRST_FINDING, "nit"), review_fixture(),
        ], max_revisions=0)
        self.assertEqual(summary["status"], "ready_for_human_review")
        self.assertTrue(summary["completed"])
        self.assertEqual(summary["remaining_major_findings"], 0)
        self.assertEqual(len(summary["outstanding_findings"]), 1)
        self.assertEqual(len(client.calls), 3)

    def test_malformed_json_gets_one_explicit_correction_then_fails(self):
        summary, client = self.execute(["{invalid", "still not JSON", draft_fixture()])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["failure_reason"], "invalid_model_output")
        self.assertFalse(summary["completed"])
        self.assertEqual(summary["correction_attempts"], 1)
        self.assertEqual(len(summary["validation_errors"]), 2)
        self.assertEqual(len(client.calls), 2)
        correction = client.calls[1]["messages"]
        self.assertEqual(correction[:2], client.calls[0]["messages"])
        self.assertEqual(correction[-2], {"role": "assistant", "content": "{invalid"})
        self.assertIn("Correct", correction[-1]["content"])
        self.assertEqual(summary["drafts"], [])
        self.assert_saved_summary(summary)

    def test_valid_correction_can_continue_the_workflow(self):
        summary, client = self.execute([
            "```json\n{}\n```", draft_fixture(), review_fixture(), review_fixture(),
        ])
        self.assertEqual(summary["status"], "ready_for_human_review")
        self.assertEqual(summary["correction_attempts"], 1)
        self.assertEqual(len(client.calls), 4)
        self.assertEqual([message["role"] for message in client.calls[2]["messages"]], ["system", "user"])

    def test_fabricated_review_evidence_is_corrected_and_never_accepted(self):
        invalid = review_fixture(FIRST_FINDING)
        invalid["findings"][0]["evidence"] = "A sentence the author did not write."
        summary, client = self.execute([draft_fixture(), review_fixture(), invalid, invalid])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["failure_reason"], "invalid_model_output")
        self.assertFalse(summary["completed"])
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(set(summary["reviews"]), {"comprehension"})
        self.assertTrue((self.run_dir / "draft-0.json").is_file())
        self.assertTrue((self.run_dir / "review-0-comprehension.json").is_file())
        self.assertFalse((self.run_dir / "review-0-design_critic.json").exists())
        self.assert_saved_summary(summary)

    def test_budget_failure_on_second_review_preserves_partial_artifacts(self):
        summary, client = self.execute([
            draft_fixture(), review_fixture(), review_fixture(),
        ], max_requests=2)
        self.assertEqual(summary["status"], "failed")
        self.assertFalse(summary["completed"])
        self.assertEqual(client.attempts, 2)
        self.assertEqual(set(summary["reviews"]), {"comprehension"})
        self.assertTrue((self.run_dir / "draft-0.json").is_file())
        self.assertTrue((self.run_dir / "review-0-comprehension.json").is_file())
        self.assert_saved_summary(summary)

    def test_revised_draft_cannot_reuse_previous_review_for_success(self):
        summary, client = self.execute([
            draft_fixture(), review_fixture(FIRST_FINDING), review_fixture(),
            draft_fixture(revised=True), review_fixture(), review_fixture(),
        ], max_requests=5)
        self.assertEqual(summary["status"], "failed")
        self.assertFalse(summary["completed"])
        self.assertEqual(summary["final_round"], 1)
        self.assertEqual(set(summary["reviews"]), {"comprehension"})
        self.assertEqual(client.attempts, 5)
        for filename in (
            "draft-0.json", "review-0-comprehension.json", "review-0-design_critic.json",
            "draft-1.json", "review-1-comprehension.json",
        ):
            self.assertTrue((self.run_dir / filename).is_file(), filename)
        self.assertFalse((self.run_dir / "review-1-design_critic.json").exists())
        self.assert_saved_summary(summary)

    def test_correction_attempt_uses_same_request_budget(self):
        summary, client = self.execute(["{invalid", draft_fixture()], max_requests=1)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(client.attempts, 1)
        self.assertEqual(summary["correction_attempts"], 1)
        self.assertFalse(summary["completed"])
        self.assert_saved_summary(summary)

    def test_revision_failure_marks_workflow_incomplete_and_preserves_prior_design(self):
        summary, client = self.execute([
            draft_fixture(), review_fixture(FIRST_FINDING), review_fixture(),
            RuntimeError("Revision transport failed"),
        ])
        self.assertEqual(summary["status"], "failed")
        self.assertFalse(summary["completed"])
        self.assertEqual(client.calls[-1]["role"], "revision")
        self.assertEqual(summary["drafts"], ["draft-0.json"])
        self.assertEqual(summary["review_artifacts"], [
            "review-0-comprehension.json", "review-0-design_critic.json",
        ])
        for filename in summary["drafts"] + summary["review_artifacts"]:
            self.assertTrue((self.run_dir / filename).is_file(), filename)
        self.assertEqual(summary["final_design"], "design.md")
        self.assertIn(draft_fixture()["design"], (self.run_dir / "design.md").read_text(encoding="utf-8"))
        self.assertFalse((self.run_dir / "draft-1.json").exists())
        self.assert_saved_summary(summary)

    def test_saved_seed_requires_two_new_reviews_and_no_author_call(self):
        summary, client = self.execute(
            [review_fixture(), review_fixture()], initial_draft=draft_fixture(revised=True),
        )
        self.assertEqual(summary["status"], "ready_for_human_review")
        self.assertEqual([call["role"] for call in client.calls], ["comprehension", "design_critic"])
        self.assertEqual(summary["revisions_used"], 0)
        self.assert_saved_summary(summary)

    def test_transport_exception_details_do_not_leak_into_report(self):
        secret = "CREDENTIAL_MUST_NOT_LEAK_e639"
        summary, _ = self.execute([RuntimeError("Network failed using key " + secret)])
        self.assertEqual(summary["status"], "failed")
        self.assertNotIn(secret, json.dumps(summary))
        self.assertNotIn(secret, (self.run_dir / "report.md").read_text(encoding="utf-8"))

    def test_duplicate_json_keys_are_not_silently_accepted(self):
        duplicate = json.dumps(draft_fixture())[:-1] + ', "title": "shadow title"}'
        summary, client = self.execute([duplicate, duplicate])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["failure_reason"], "invalid_model_output")
        self.assertEqual(len(client.calls), 2)


if __name__ == "__main__":
    unittest.main()
