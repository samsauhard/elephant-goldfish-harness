"""Live, frozen paired comparison; the one-call baseline reuses its first sample."""
import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.grading import match_defects, metrics
from harness_lab.__main__ import load_json, new_run, write_metadata
from harness_lab.client import LocalClient
from harness_lab.contracts import validate_review
from harness_lab.prompts import REVIEW_CONTRACT
from harness_lab.runtime import _structured_call, run

ARMS = ("generic_one", "generic_two", "egm_two")


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def generic_messages(case):
    contract = REVIEW_CONTRACT.replace(
        "The upstream rubric/persona governs substantive review. This adapter replaces only its\nplain-language output format and unavailable file/tool instructions.",
        "Review the design for correctness, security, reliability, clarity, scope, and testability against the supplied references."
    )
    return [{"role": "system", "content": "You are a software design reviewer.\n" + contract},
            {"role": "user", "content": json.dumps({"draft": case["draft"], "references": case["task"]["references"]})}]


def generic_round(case, client, path):
    summary = {"validation_errors": [], "correction_attempts": 0}
    findings = []
    first = None
    completed = False
    for index in range(2):
        try:
            review = _structured_call(client, generic_messages(case), "generic_" + str(index + 1),
                                      lambda candidate: validate_review(candidate, case["draft"]),
                                      summary, "generic_" + str(index + 1))
            findings.extend(dict(f, persona="generic_" + str(index + 1)) for f in review["findings"])
            save(path / ("review-" + str(index + 1) + ".json"), review)
            completed = True
        except Exception as exc:
            completed = False
            summary["exception_type"] = type(exc).__name__
        result = dict(summary, completed=completed, outstanding_findings=copy.deepcopy(findings),
                      status=("needs_attention" if any(f["severity"] in ("major", "blocker") for f in findings)
                              else "ready_for_human_review") if completed else "failed")
        if index == 0:
            first = {"result": copy.deepcopy(result), "attempts": client.attempts,
                     "total_tokens": client.usage.get("total_tokens", 0),
                     "resolved_models": sorted(client.resolved_models)}
            save(path / "first-result.json", result)
        if not completed:
            break
    save(path / "result.json", result)
    return result, first


def make_row(case, arm, result, attempts, tokens, models, path, trial):
    complete = result.get("completed", False)
    findings = result.get("outstanding_findings", [])
    matches = match_defects(case, findings)
    return {
        "case": case["id"], "family": case["family"], "trial": trial, "arm": arm,
        "completed": complete, "status": result["status"], "expected": len(case["expected"]),
        "detected": sum(bool(indices) for indices in matches.values()) if complete else None,
        "matches": matches, "major_findings": sum(f["severity"] in ("major", "blocker") for f in findings),
        "attempts": attempts, "total_tokens": tokens, "resolved_models": models,
        "validation_errors": len(result.get("validation_errors", [])),
        "result": str(path),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.local.json")
    parser.add_argument("--output", default="runs")
    parser.add_argument("--model", default="gpt-oss-120b")
    parser.add_argument("--trials", type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args(argv)
    config = load_json(args.config)
    config.update(model=args.model, max_requests=8, max_output_tokens=3000, timeout_seconds=120)
    cases = load_json(ROOT / "examples/hard-evaluation.json")
    output = new_run(args.output, "hard-benchmark")
    schedule = [(case, trial, arm) for trial in range(1, args.trials + 1)
                for index, case in enumerate(cases)
                for arm in (("generic_two", "egm_two") if (index + trial) % 2 else ("egm_two", "generic_two"))]
    sources = ["examples/hard-evaluation.json", "benchmarks/hard_cases.py", "benchmarks/grading.py",
               "scripts/run_hard_benchmark.py", "harness_lab/prompts.py", "harness_lab/contracts.py",
               "harness_lab/runtime.py", "harness_lab/client.py"]
    protocol = {
        "mode": "live", "requested_model": args.model, "trials": args.trials,
        "created_before_requests": True, "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        "schedule": [[case["id"], trial, arm] for case, trial, arm in schedule],
        "arms": {"generic_one": "First sample of generic_two; not an independent replicate.",
                 "generic_two": "Two independent strong generic reviews; same schema, references, limits, and validation as EGM.",
                 "egm_two": "Existing unmodified comprehension and design-critic runtime, max_revisions=0."},
        "primary_metric": "Detected planted flaws in completed reviews / all planted flaws. A failed review delivers zero verified detections and remains in the denominator.",
        "grading": "Predeclared evidence localization plus conjunctive causal-concept patterns; matches are diagnostic and need semantic audit. No model judge sees the labels.",
        "controls": "Three defective/corrected pairs. Major findings on corrected controls are false-positive candidates, not automatically errors.",
        "budgets": "Two-call arms have equal logical call and output-token limits, not equal actual input/output tokens. Corrections and retries consume budget.",
        "limitations": "Synthetic cases, constructed for this experiment; one trial by default; no population-level accuracy or significance claim. Providers may vary under the pinned model group and are recorded.",
        "exclusions": "No failed or unfavorable case is dropped. No dataset, prompt, or grader tuning after generation starts.",
    }
    save(output / "protocol.json", protocol)
    for name in sources:
        target = output / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    print("Experiment: " + str(output), flush=True)
    rows = []
    last_dispatch = None
    for case, trial, arm in schedule:
        path = output / (case["id"] + "-trial-" + str(trial) + "-" + arm)
        path.mkdir()
        client = LocalClient(config, path, last_dispatch=last_dispatch)
        print("Starting " + path.name, flush=True)
        started = time.monotonic()
        if arm == "egm_two":
            result = run(case["task"], client, path, max_revisions=0, initial_draft=case["draft"])
        else:
            result, first = generic_round(case, client, path)
            rows.append(make_row(case, "generic_one", first["result"], first["attempts"], first["total_tokens"],
                                 first["resolved_models"], path / "first-result.json", trial))
        last_dispatch = client.last_dispatch
        write_metadata(path, client, config)
        row = make_row(case, arm, result, client.attempts, client.usage.get("total_tokens", 0),
                       sorted(client.resolved_models), path / "result.json", trial)
        row["elapsed_seconds"] = round(time.monotonic() - started, 2)
        rows.append(row)
        snapshot = {"protocol": protocol, "rows": rows, "metrics": {arm: metrics(rows, arm) for arm in ARMS}}
        save(output / "comparison.json", snapshot)
        print(json.dumps(row), flush=True)
    print("Results: " + str(output / "comparison.json"), flush=True)
    return 0 if all(row["completed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
