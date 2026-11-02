"""Summarize a completed frozen run without changing its grader or selecting cases."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness_lab.contracts import validate_review
from harness_lab.runtime import _decode


def repair_outcomes(directory, cases):
    rows = []
    for trace in sorted(directory.glob('*/trace.jsonl')):
        case_id = trace.parent.name.split('-trial-')[0]
        if case_id not in cases:
            continue
        events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        roles = list(dict.fromkeys(e['role'] for e in events if e['event'] == 'request'))
        for role in roles:
            outcomes = [e for e in events if e.get('role') == role and e['event'] in ('response','error')]
            def valid(event):
                if not event or event['event'] != 'response':
                    return False
                try:
                    validate_review(_decode(event['text']), cases[case_id]['draft'])
                    return True
                except (ValueError, KeyError, TypeError):
                    return False
            first_valid = valid(outcomes[0]) if outcomes else False
            final_valid = valid(outcomes[-1]) if outcomes else False
            rows.append({'case':case_id, 'directory':trace.parent.name, 'role':role,
                         'first_valid':first_valid, 'final_valid':final_valid,
                         'repaired':not first_valid and final_valid,
                         'http_errors':sum(e['event']=='error' for e in outcomes),
                         'routing':sorted({e.get('routed_via') for e in outcomes if e.get('routed_via')})})
    return rows


def percent(n, d):
    return str(n)+'/'+str(d)+' ('+format(100*n/d,'.1f')+'%)' if d else 'not measured'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory')
    args=parser.parse_args(argv)
    directory=Path(args.run_directory).resolve()
    data=json.loads((directory/'comparison.json').read_text(encoding='utf-8'))
    expected_rows=len(data['protocol']['schedule'])//2*3
    if len(data['rows']) != expected_rows:
        raise ValueError('Experiment is incomplete; do not write a final report yet')
    cases={c['id']:c for c in json.loads((directory/'sources/examples/hard-evaluation.json').read_text(encoding='utf-8'))}
    repairs=repair_outcomes(directory,cases)
    first=sum(row['first_valid'] for row in repairs)
    final=sum(row['final_valid'] for row in repairs)
    repaired=sum(row['repaired'] for row in repairs)
    repair_summary={'invocations':len(repairs),'first_valid':first,'final_valid':final,
                    'repaired':repaired,'rows':repairs}
    (directory/'repair-outcomes.json').write_text(json.dumps(repair_summary,indent=2)+'\n',encoding='utf-8')
    m=data['metrics']
    arms=('generic_one','generic_two','egm_two')
    lines=['# Harder live review benchmark','',
           'Six synthetic designs in three defective/corrected pairs; six planted faults; '+str(data['protocol']['trials'])+' trial(s) per case. All generations are live. No favorable-case selection or post-generation grader changes.',
           '', '| Metric | One generic review | Two generic reviews | Two EGM reviews |',
           '| --- | ---: | ---: | ---: |']
    for label, render in (
        ('Automatic seeded detection',lambda r:percent(r['detected_defects'],r['expected_defects'])),
        ('Completed case reviews',lambda r:percent(r['completed'],r['case_trials'])),
        ('Corrected counterparts with major alerts',lambda r:percent(r['controls_with_major_alerts'],r['completed_clean_controls'])),
        ('Reported tokens',lambda r:format(r['reported_total_tokens'],',')),
        ('HTTP attempts',lambda r:str(r['http_attempts'])),
    ):
        lines.append('| '+label+' | '+' | '.join(render(m[arm]) for arm in arms)+' |')
    lines += ['', 'One generic review reuses the first sample of the two-review arm. The two-call arms have equal call/output limits but not equal actual token consumption. These are automatic diagnostic scores pending semantic audit; evidence/keyword matching is not an independent judge.',
              '', '## Validation and bounded repair', '',
              '- Valid response on the first attempt: '+percent(first,len(repairs))+'.',
              '- Valid response after allowed corrections/retries: '+percent(final,len(repairs))+'.',
              '- Initially invalid or failed invocations repaired: '+str(repaired)+'.',
              '- These checks cover JSON structure and exact citation grounding, not whether the criticism is correct. Both generic and EGM methods use this harness feature; credit cannot be assigned to EGM personas alone.',
              '', '## Every case', '',
              '| Case | Expected faults | One generic | Two generic | EGM |',
              '| --- | ---: | ---: | ---: | ---: |']
    for case_id in cases:
        for trial in range(1,data['protocol']['trials']+1):
            rows={r['arm']:r for r in data['rows'] if r['case']==case_id and r['trial']==trial}
            values=[str(rows[arm]['detected']) if rows[arm]['completed'] else 'failed' for arm in arms]
            lines.append('| '+case_id+' / '+str(trial)+' | '+str(len(cases[case_id]['expected']))+' | '+' | '.join(values)+' |')
    routes=sorted({route for row in repairs for route in row['routing']})
    lines += ['', '## Limits and evidence', '',
              '- Only three scenario families, constructed for this test; no general accuracy or statistical-superiority claim.',
              '- A corrected counterpart repairs the seeded faults, but may contain additional flaws. A major-alert rate is not a false-positive rate without adjudication. See the separate audit notes.',
              '- Actual provider routes: '+', '.join('`'+route+'`' for route in routes)+'. Provider changes limit causal attribution.',
              '- Elapsed times include configured pacing. No dollar cost is inferred from token counts.',
              '- [Protocol](protocol.json), [source snapshots](sources/), [all results](comparison.json), [repair measurements](repair-outcomes.json), [semantic audit notes](audit-notes.md).', '']
    (directory/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(directory/'report.md')
    print(json.dumps({'first_valid':first,'final_valid':final,'invocations':len(repairs),'repaired':repaired}))


if __name__ == '__main__':
    main()
