import copy
import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.grading import match_defects, metrics
from benchmarks.hard_cases import build_cases, counterexamples
from harness_lab.contracts import validate_draft, validate_task
from scripts.run_hard_benchmark import generic_messages
from scripts.report_hard_benchmark import repair_outcomes


class HardBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.cases = build_cases()

    def test_dataset_has_three_corrected_pairs_and_six_distinct_faults(self):
        saved = json.loads((Path(__file__).resolve().parents[1]/'examples/hard-evaluation.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, self.cases)
        self.assertEqual(len(self.cases), 6)
        faults = [f['id'] for c in self.cases for f in c['expected']]
        self.assertEqual(len(set(faults)), 6)
        for case in self.cases:
            validate_task(case['task'])
            validate_draft(case['draft'])
        for family in ('feed', 'worker', 'expiry'):
            self.assertEqual(sorted(len(c['expected']) for c in self.cases if c['family']==family), [0,2])
        self.assertEqual(set(counterexamples()), set(faults))
        self.assertTrue(all(row['broken'] and row['fixed'] for row in counterexamples().values()))

    def test_expected_labels_and_witnesses_never_enter_requests(self):
        for case in self.cases:
            messages = generic_messages(case)
            payload = json.loads(messages[1]['content'])
            self.assertEqual(set(payload), {'draft','references'})
            self.assertEqual(payload['draft'], case['draft'])
            self.assertEqual(payload['references'], case['task']['references'])
            for expected in case['expected']:
                self.assertNotIn(expected['counterexample'], json.dumps(messages))

    def test_localization_alone_does_not_count_as_detection(self):
        case = next(c for c in self.cases if c['id']=='case-17')
        unrelated = {'evidence':'Successful pages are cached', 'issue':'The cache needs a glossary.', 'recommendation':'Define this word.'}
        self.assertFalse(any(match_defects(case, [unrelated]).values()))
        real = dict(unrelated, issue='The shared cache key omits the tenant and leaks customer data.', recommendation='Partition cache keys by authenticated tenant.')
        self.assertEqual(match_defects(case, [real, real])['tenant-cache'], [0,1])
        # Repeated findings remain one flaw in the row, rather than two hits.
        self.assertEqual(sum(bool(indices) for indices in match_defects(case, [real,real]).values()), 1)

    def test_failed_cases_remain_in_primary_denominator(self):
        base={'arm':'egm_two','expected':2,'completed':True,'detected':2,'major_findings':2,'attempts':2,'total_tokens':100,'validation_errors':0}
        failed=dict(base, completed=False, detected=None)
        result=metrics([base,failed], 'egm_two')
        self.assertEqual(result['delivered_detection_percent'],50)
        self.assertEqual(result['completion_percent'],50)
        self.assertIsNone(result['clean_control_major_alert_percent'])

    def test_failed_clean_control_is_not_scored_as_no_false_alarm(self):
        row={'arm':'egm_two','expected':0,'completed':False,'detected':None,'major_findings':0,'attempts':2,'total_tokens':100,'validation_errors':1}
        result=metrics([row],'egm_two')
        self.assertEqual(result['completed_clean_controls'],0)
        self.assertIsNone(result['clean_control_major_alert_percent'])
        self.assertIsNone(result['delivered_detection_percent'])

    def test_correction_counts_as_one_invocation_not_two_independent_reviews(self):
        case = next(c for c in self.cases if c['id']=='case-17')
        bad={'summary':'Review','findings':[{'severity':'major','category':'security','section':'design','evidence':'fabricated quotation','issue':'Cache omits tenant.','recommendation':'Add tenant to key.'}]}
        good=copy.deepcopy(bad)
        good['findings'][0]['evidence']='Successful pages are cached for 30 seconds'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'case-17-trial-1-egm_two'
            path.mkdir()
            events=[{'event':'request','role':'comprehension'},
                    {'event':'response','role':'comprehension','text':json.dumps(bad)},
                    {'event':'request','role':'comprehension'},
                    {'event':'response','role':'comprehension','text':json.dumps(good)}]
            (path/'trace.jsonl').write_text('\n'.join(json.dumps(e) for e in events),encoding='utf-8')
            rows=repair_outcomes(Path(directory),{'case-17':case})
        self.assertEqual(len(rows),1)
        self.assertFalse(rows[0]['first_valid'])
        self.assertTrue(rows[0]['final_valid'])
        self.assertTrue(rows[0]['repaired'])

    def test_transport_failure_without_review_is_not_counted_as_valid(self):
        case=self.cases[0]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/(case['id']+'-trial-1-generic_two')
            path.mkdir()
            events=[{'event':'request','role':'generic_1'}, {'event':'error','role':'generic_1','error':'timeout'}]
            (path/'trace.jsonl').write_text('\n'.join(json.dumps(e) for e in events),encoding='utf-8')
            rows=repair_outcomes(Path(directory),{case['id']:case})
        self.assertEqual(len(rows),1)
        self.assertFalse(rows[0]['first_valid'])
        self.assertFalse(rows[0]['final_valid'])
        self.assertFalse(rows[0]['repaired'])


if __name__ == '__main__':
    unittest.main()
