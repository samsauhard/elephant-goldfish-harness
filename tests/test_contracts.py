"""Deterministic structure and grounding tests; no model-quality claims."""
import copy
import unittest

from harness_lab.contracts import validate_draft, validate_review, validate_task


def draft_fixture():
    return {
        "title": "Create export jobs",
        "problem": "Customers need an asynchronous export API.",
        "goals": ["Accept a bounded export request", "Return a stable job ID"],
        "design": "POST /exports creates a job. Clients retry failed requests.",
        "alternatives": ["A synchronous export would hold connections open."],
        "risks": ["Retries may create duplicate jobs."],
        "acceptance_tests": ["A valid request returns HTTP 202 and a job ID."],
        "open_questions": [],
    }


def review_fixture(**changes):
    finding = {
        "severity": "major",
        "category": "reliability",
        "section": "design",
        "evidence": "Clients retry failed requests.",
        "issue": "Retrying a creation request may create duplicate jobs.",
        "recommendation": "Specify idempotency keys and duplicate-request behavior.",
    }
    finding.update(changes)
    return {"summary": "The retry contract needs clarification.", "findings": [finding]}


class ContractTests(unittest.TestCase):
    def test_complete_draft_and_empty_open_questions_are_valid(self):
        validate_draft(draft_fixture())
        validate_review({"summary": "No grounded findings.", "findings": []}, draft_fixture())

    def test_task_requires_inline_string_references(self):
        task = {"title": "Export API", "brief": "Design export jobs.", "references": []}
        validate_task(task)
        validate_task(dict(task, planning_notes="Private author notes"))
        for references in ("not a list", [{"path": "secrets.txt"}], ["  "], [False]):
            with self.subTest(references=references), self.assertRaises(ValueError):
                validate_task(dict(task, references=references))

    def test_non_objects_and_missing_fields_are_rejected(self):
        for value in (None, False, [], "draft"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_draft(value)
        for field in draft_fixture():
            draft = draft_fixture()
            del draft[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                validate_draft(draft)

    def test_required_text_and_lists_are_nonempty_and_typed(self):
        for field in ("title", "problem", "design"):
            for value in ("", " \n\t", False, 42, []):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_draft(dict(draft_fixture(), **{field: value}))
        for field in ("goals", "alternatives", "risks", "acceptance_tests"):
            for value in ([], "text", [" "], [False], [42], [None]):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_draft(dict(draft_fixture(), **{field: value}))
        for value in ("", [" "], [False]):
            with self.subTest(open_questions=value), self.assertRaises(ValueError):
                validate_draft(dict(draft_fixture(), open_questions=value))

    def test_exact_quote_is_required_in_named_section(self):
        validate_review(review_fixture(), draft_fixture())
        invalid = (
            {"evidence": "clients retry failed requests."},
            {"evidence": "Clients  retry failed requests."},
            {"evidence": "Idempotency keys expire after 24 hours."},
            {"evidence": " "},
            {"section": "problem"},
            {"section": "planning_notes"},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_review(review_fixture(**changes), draft_fixture())

    def test_list_evidence_matches_one_real_entry(self):
        draft = draft_fixture()
        validate_review(review_fixture(section="goals", evidence="bounded export request"), draft)
        # Joining or JSON-serializing the list must not manufacture valid evidence.
        for evidence in (
            'request", "Return',
            "request Return",
            "request\nReturn",
            '["Accept a bounded export request"',
        ):
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                validate_review(review_fixture(section="goals", evidence=evidence), draft)

    def test_review_enums_and_required_strings_are_checked(self):
        invalid = (
            {"severity": "critical"},
            {"category": "performance"},
            {"section": "missing"},
            {"issue": ""},
            {"recommendation": "  "},
            {"evidence": False},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_review(review_fixture(**changes), draft_fixture())
        for field in review_fixture()["findings"][0]:
            review = review_fixture()
            del review["findings"][0][field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                validate_review(review, draft_fixture())

    def test_reviews_require_summary_and_a_bounded_findings_list(self):
        finding = review_fixture()["findings"][0]
        validate_review({"summary": "Twelve findings.", "findings": [finding] * 12}, draft_fixture())
        for review in (
            {"summary": "Too many.", "findings": [finding] * 13},
            {"summary": "", "findings": []},
            {"summary": "No list.", "findings": {}},
            {"summary": "Bad entry.", "findings": [None]},
            {"summary": "Missing findings."},
        ):
            with self.subTest(review=review), self.assertRaises(ValueError):
                validate_review(review, draft_fixture())

    def test_validation_does_not_mutate_supplied_artifacts(self):
        draft, review = draft_fixture(), review_fixture()
        original = copy.deepcopy((draft, review))
        validate_review(review, draft)
        self.assertEqual((draft, review), original)


if __name__ == "__main__":
    unittest.main()
