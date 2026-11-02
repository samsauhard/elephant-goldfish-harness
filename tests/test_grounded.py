import copy
import json
from pathlib import Path
import tempfile
import unittest

from harness_lab.grounded import normalize_review, reviewer_messages, source_map
from harness_lab.runtime import run
from test_runtime import FakeClient, PRIVATE_NOTES, draft_fixture, task_fixture


def finding_fixture(draft=None, references=None):
    draft = draft or draft_fixture()
    references = task_fixture()["references"] if references is None else references
    sources = source_map(draft, references)
    passage = next(p for p in sources["draft_passages"] if p["section"] == "design")
    return {"summary": "A proposed counterexample, not proof.", "findings": [{
        "severity": "major", "category": "security", "passage_id": passage["id"],
        "requirement_ids": [sources["requirement_sources"][-1]["id"]],
        "issue": "PRIVATE_REVIEW_MARKER: tenant ownership is not specified.",
        "recommendation": "Check ownership before reading an export.",
        "counterexample": {"scenario": "Tenant B requests tenant A's export ID.",
                           "violation": "Returning A's export would violate tenant isolation."},
    }]}


class GroundedTests(unittest.TestCase):
    def setUp(self):
        self.draft = draft_fixture()
        self.refs = task_fixture()["references"]

    def normalize(self, review):
        return normalize_review(review, self.draft, self.refs)

    def test_citation_resolves_exact_unicode_text_without_model_quotation(self):
        self.draft["design"] = "First paragraph.\n\nSecond — ‘quoted’ line.\nNo normalization."
        sources = source_map(self.draft, self.refs)
        passage = next(p for p in sources["draft_passages"] if "Second" in p["text"])
        review = finding_fixture(self.draft)
        review["findings"][0]["passage_id"] = passage["id"]
        normalized = self.normalize(review)
        self.assertEqual(normalized["findings"][0]["evidence"], "Second — ‘quoted’ line.\nNo normalization.")
        self.assertEqual(normalized["findings"][0]["section"], "design")

    def test_list_boundaries_and_duplicate_text_keep_distinct_ids(self):
        self.draft["goals"] = ["Same text", "Same text"]
        self.draft["risks"] = ["Same text"]
        sources = source_map(self.draft, self.refs)
        passages = [p for p in sources["draft_passages"] if p["text"] == "Same text"]
        self.assertEqual(len({p["id"] for p in passages}), 3)
        review = finding_fixture(self.draft)
        review["findings"][0]["passage_id"] = passages[-1]["id"]
        normalized = self.normalize(review)
        self.assertEqual(normalized["findings"][0]["section"], "risks")
        self.assertEqual(normalized["findings"][0]["evidence"], "Same text")

    def test_ids_are_stable_but_bound_to_whole_document_and_references(self):
        original = source_map(self.draft, self.refs)
        reordered = dict(reversed(list(self.draft.items())))
        self.assertEqual(original, source_map(reordered, self.refs))
        review = finding_fixture()
        for changed_draft, changed_refs in ((dict(self.draft, title="Revised title"), self.refs),
                                            (self.draft, self.refs + ["A new scope limit"])):
            with self.assertRaisesRegex(ValueError, "current draft"):
                normalize_review(review, changed_draft, changed_refs)

    def test_invented_passage_or_reference_as_passage_fails(self):
        for value in ("invented", source_map(self.draft, self.refs)["requirement_sources"][-1]["id"]):
            review = finding_fixture()
            review["findings"][0]["passage_id"] = value
            with self.assertRaisesRegex(ValueError, "current draft"):
                self.normalize(review)

    def test_major_requires_requirement_and_nonempty_failure_scenario(self):
        for change in ({"requirement_ids": []}, {"counterexample": None},
                       {"counterexample": {"scenario": " ", "violation": "failure"}},
                       {"counterexample": {"scenario": "failure", "violation": " "}},
                       {"counterexample": {"scenario": "failure"}}):
            review = finding_fixture()
            review["findings"][0].update(change)
            with self.assertRaises(ValueError):
                self.normalize(review)

    def test_unknown_duplicate_or_design_requirement_ids_fail(self):
        review = finding_fixture()
        valid = review["findings"][0]["requirement_ids"][0]
        design = review["findings"][0]["passage_id"]
        for ids in (["unknown"], [valid, valid], [design], [{}], "not a list"):
            review["findings"][0]["requirement_ids"] = ids
            with self.assertRaises(ValueError):
                self.normalize(review)

    def test_nit_can_have_no_requirement_or_witness_without_being_dropped(self):
        review = finding_fixture()
        review["findings"][0].update(severity="nit", requirement_ids=[], counterexample=None)
        normalized = self.normalize(review)
        self.assertEqual(len(normalized["findings"]), 1)
        self.assertEqual(normalized["findings"][0]["severity"], "nit")

    def test_invalid_schema_does_not_bypass_legacy_severity_or_category_checks(self):
        for field, value in (("severity", "critical"), ("category", "invented"), ("issue", ""), ("extra", "field")):
            review = finding_fixture()
            review["findings"][0][field] = value
            with self.assertRaises(ValueError):
                self.normalize(review)

    def test_new_revision_regenerates_ids_and_keeps_reviewers_isolated(self):
        empty = {"summary": "No remaining findings.", "findings": []}
        raw = finding_fixture()
        client = FakeClient([raw, empty, draft_fixture(True), empty, empty])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            summary = run(task_fixture(), client, path, initial_draft=self.draft, review_mode="grounded")
            self.assertTrue(summary["completed"])
            self.assertEqual(summary["status"], "ready_for_human_review")
            self.assertEqual(summary["revisions_used"], 1)
            for index in (0, 1, 3, 4):
                messages = client.calls[index]["messages"]
                self.assertEqual([m["role"] for m in messages], ["system", "user"])
                self.assertNotIn(PRIVATE_NOTES, json.dumps(messages))
                self.assertNotIn("PRIVATE_REVIEW_MARKER", json.dumps(messages))
            self.assertIn("PRIVATE_REVIEW_MARKER", json.dumps(client.calls[2]["messages"]))
            self.assertIn("scenario", json.dumps(client.calls[2]["messages"]))
            first = json.loads((path / "grounding-0.json").read_text())
            second = json.loads((path / "grounding-1.json").read_text())
            self.assertNotEqual(first["document_sha256"], second["document_sha256"])
            self.assertEqual(json.loads((path / "review-0-comprehension-grounded.json").read_text()), raw)
            self.assertEqual(json.loads(client.calls[3]["messages"][1]["content"]), second)

    def test_unresolved_ids_fail_closed_after_one_correction(self):
        raw = finding_fixture()
        raw["findings"][0]["passage_id"] = "unknown"
        client = FakeClient([raw, raw])
        with tempfile.TemporaryDirectory() as directory:
            summary = run(task_fixture(), client, Path(directory), initial_draft=self.draft, review_mode="grounded")
            self.assertFalse(summary["completed"])
            self.assertEqual(summary["failure_reason"], "invalid_model_output")
            self.assertEqual(client.attempts, 2)
            self.assertEqual(summary["reviews"], {})
            self.assertTrue((Path(directory) / "grounding-0.json").exists())

    def test_corrected_id_keeps_finding_and_report_keeps_argument(self):
        raw = finding_fixture()
        bad = copy.deepcopy(raw)
        bad["findings"][0]["passage_id"] = "unknown"
        client = FakeClient([bad, raw, {"summary": "No findings", "findings": []}])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            summary = run(task_fixture(), client, path, initial_draft=self.draft, max_revisions=0, review_mode="grounded")
            self.assertEqual(summary["status"], "needs_attention")
            self.assertEqual(summary["remaining_major_findings"], 1)
            self.assertEqual(summary["correction_attempts"], 1)
            self.assertIn(raw["findings"][0]["counterexample"]["scenario"], (path / "report.md").read_text())

    def test_missing_mode_never_dispatches(self):
        client = FakeClient([])
        with tempfile.TemporaryDirectory() as directory:
            summary = run(task_fixture(), client, Path(directory), initial_draft=self.draft, review_mode="typo")
        self.assertEqual(summary["failure_reason"], "invalid_input")
        self.assertEqual(client.attempts, 0)


if __name__ == "__main__":
    unittest.main()
