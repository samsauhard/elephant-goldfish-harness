"""Frozen grounded-mode regression plus a fresh paired legacy/grounded comparison."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.grading import metrics
from harness_lab.__main__ import load_json, new_run, write_metadata
from harness_lab.client import LocalClient
from harness_lab.runtime import run
from scripts.run_hard_benchmark import make_row, save


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.local.json")
    parser.add_argument("--output", default="runs")
    parser.add_argument("--model", default="gpt-oss-120b")
    args = parser.parse_args(argv)
    config = load_json(args.config)
    config.update(model=args.model, max_requests=6, max_output_tokens=3000, timeout_seconds=120)
    existing = load_json(ROOT / "examples/hard-evaluation.json")
    transfer = load_json(ROOT / "examples/grounded-transfer.json")
    # No labels or case IDs enter runtime inputs. Counterbalance the fresh pair.
    schedule = [(case, "development", "grounded") for case in existing]
    schedule += [(case, "transfer", mode) for index, case in enumerate(transfer)
                 for mode in (("legacy", "grounded") if index % 2 == 0 else ("grounded", "legacy"))]
    sources = ["examples/hard-evaluation.json", "examples/grounded-transfer.json",
               "benchmarks/hard_cases.py", "benchmarks/grounded_cases.py", "benchmarks/grading.py",
               "scripts/run_grounded_benchmark.py", "scripts/run_hard_benchmark.py",
               "harness_lab/__main__.py", "harness_lab/grounded.py", "harness_lab/prompts.py",
               "harness_lab/contracts.py", "harness_lab/runtime.py", "harness_lab/client.py"]
    protocol = {
        "requested_model": args.model, "trials": 1, "created_before_requests": True,
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
        "schedule": [[case["id"], suite, mode] for case, suite, mode in schedule],
        "development": "Six unchanged previously observed cases. Compare exploratorily to the archived legacy EGM run, not a concurrent control. Known unseeded retry-count flaw in case-26 is retained.",
        "transfer": "One new synthetic defective/corrected inventory pair, two seeded flaws, frozen before live requests. Both modes get two independent EGM calls; execution order is counterbalanced. Authored here, not an independent external test set.",
        "grading": "Use the existing frozen evidence-plus-causal-concepts matcher and manually audit all major findings, including unmatched findings. Failed reviews deliver zero detections and remain in the denominator. Control alerts are not automatically false positives.",
        "budgets": "Same model group, output limit 3000, max six HTTP attempts per case/mode, one correction per review, zero revisions. Actual tokens differ. All attempts, returned models, and provider routes are retained.",
        "exclusions": "Keep every case and failure. No prompt, fixture, or grader tuning after requests start. Preserve original hard benchmark and raw outputs.",
        "limitations": "Small synthetic samples, one trial, no statistical generalization; provider failover may confound comparisons. Requirement IDs and witnesses establish structure/provenance, not semantic correctness.",
    }
    output = new_run(args.output, "grounded-benchmark")
    save(output / "protocol.json", protocol)
    for name in sources:
        target = output / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    print("Experiment: " + str(output), flush=True)
    rows = []
    last_dispatch = None
    for case, suite, mode in schedule:
        path = output / (case["id"] + "-" + mode)
        path.mkdir()
        case_config = dict(config, review_mode=mode)
        client = LocalClient(case_config, path, last_dispatch=last_dispatch)
        print("Starting " + path.name, flush=True)
        started = time.monotonic()
        result = run(case["task"], client, path, max_revisions=0, initial_draft=case["draft"], review_mode=mode)
        last_dispatch = client.last_dispatch
        write_metadata(path, client, case_config)
        row = make_row(case, mode, result, client.attempts,
                       client.usage.get("total_tokens", 0), sorted(client.resolved_models), path.name, 1)
        row.update(suite=suite, elapsed_seconds=round(time.monotonic() - started, 2))
        rows.append(row)
        save(output / "comparison.json", {"protocol": protocol, "rows": rows,
             "metrics": {suite_name: {arm: metrics([r for r in rows if r["suite"] == suite_name], arm)
                                     for arm in ("legacy", "grounded")}
                         for suite_name in ("development", "transfer")}})
        print(json.dumps(row), flush=True)
    print("Results: " + str(output / "comparison.json"), flush=True)
    return 0 if all(row["completed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
