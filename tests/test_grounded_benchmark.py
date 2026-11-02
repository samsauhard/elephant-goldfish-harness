import json
from pathlib import Path
import unittest

from benchmarks.grounded_cases import build_cases
from benchmarks.grading import match_defects
from harness_lab.contracts import validate_draft, validate_task
from harness_lab.grounded import reviewer_messages, source_map
from scripts.report_grounded_benchmark import invocation_outcomes


class GroundedBenchmarkTests(unittest.TestCase):
    def test_frozen_transfer_pair_and_hidden_labels(self):
        cases = build_cases()
        saved = json.loads((Path(__file__).resolve().parents[1] / "examples/grounded-transfer.json").read_text())
        self.assertEqual(cases, saved)
        self.assertEqual([len(c["expected"]) for c in cases], [0, 2])
        self.assertEqual(cases[0]["task"], cases[1]["task"])
        for case in cases:
            validate_task(case["task"])
            validate_draft(case["draft"])
            sources = source_map(case["draft"], case["task"]["references"])
            for persona in ("comprehension", "design_critic"):
                request = json.dumps(reviewer_messages(sources, persona))
                for defect in case["expected"]:
                    self.assertNotIn(defect["counterexample"], request)
                self.assertNotIn(case["id"], request)

    def test_long_citation_and_short_quote_receive_same_seeded_match(self):
        bad = build_cases()[1]
        full = bad["expected"][0]["anchors"][0]
        text = {"issue": "Two concurrent reservations decrement available stock below zero, allowing over-allocation.",
                "recommendation": "Use a guarded atomic UPDATE for available stock."}
        for evidence in (full, "The separate read is the admission check."):
            matches = match_defects(bad, [dict(text, evidence=evidence)])
            self.assertEqual(matches["over-allocation"], [0])
            self.assertEqual(matches["repeat-cancellation"], [])

    def test_absent_second_review_is_not_a_successful_invocation(self):
        case = build_cases()[0]
        events = [{"event": "response", "role": "comprehension", "text": '{"summary":"Clear","findings":[]}'}]
        rows = invocation_outcomes(events, case, "grounded")
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["final_valid"])
        self.assertFalse(rows[1]["dispatched"])
        self.assertFalse(rows[1]["first_attempt_valid"])
        self.assertFalse(rows[1]["final_valid"])

    def test_transport_retry_and_schema_correction_are_distinct(self):
        case = build_cases()[0]
        valid = '{"summary":"Clear","findings":[]}'
        events = [{"event": "error", "role": "comprehension"},
                  {"event": "response", "role": "comprehension", "text": valid},
                  {"event": "response", "role": "design_critic", "text": "invalid JSON"},
                  {"event": "response", "role": "design_critic", "text": valid}]
        rows = invocation_outcomes(events, case, "grounded")
        self.assertFalse(rows[0]["first_attempt_valid"])
        self.assertTrue(rows[0]["first_response_valid"])
        self.assertFalse(rows[0]["validation_repaired"])
        self.assertTrue(rows[1]["validation_repaired"])
        self.assertTrue(all(r["final_valid"] for r in rows))


if __name__ == "__main__":
    unittest.main()
