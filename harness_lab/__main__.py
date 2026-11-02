"""Run from the repository root with python -m harness_lab."""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .client import LocalClient, ModelError, ScriptedClient
from .prompts import ROOT
from .runtime import run


def load_json(path):
    path = Path(path)
    if path.stat().st_size > 100_000:
        raise ValueError("Input JSON file exceeds 100 KB")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def new_run(output, label):
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + label + "-" + uuid4().hex[:8]
    path = Path(output) / name
    path.mkdir(parents=True, exist_ok=False)
    return path.resolve()


def write_metadata(path, client, config):
    safe_config = {k: v for k, v in config.items() if k in (
        "base_url", "model", "json_mode", "max_requests", "max_output_tokens",
        "timeout_seconds", "transport_retries", "min_interval_seconds", "review_mode")}
    metadata = {"mode": client.mode, "configuration": safe_config, "attempts": client.attempts,
                "usage": client.usage if client.usage_available else None,
                "resolved_models": sorted(getattr(client, "resolved_models", [])),
                "cost_usd": None, "note": "Cost not reported or estimated. Router aliases may select different models.",
                "source_sha256": {name: hashlib.sha256((ROOT / "harness_lab" / name).read_bytes()).hexdigest()
                                  for name in ("runtime.py", "contracts.py", "prompts.py", "client.py", "grounded.py")},
                "egm": json.loads((ROOT / "vendor/elephant-goldfish/UPSTREAM.json").read_text(encoding="utf-8"))}
    (path / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def print_result(result, path):
    print("Status: " + result["status"])
    print("Mode: " + result.get("mode", "unknown"))
    print("Report: " + str(path / "report.md"))
    print("Trace: " + str(path / "trace.jsonl"))
    if result.get("failure_reason"):
        print("Reason: " + result["failure_reason"])


def evaluation(args, config):
    dataset = load_json(ROOT / "examples/evaluation.json")
    if args.case:
        dataset = [case for case in dataset if case["id"] == args.case]
        if not dataset:
            raise ValueError("Unknown evaluation case")
    output = new_run(args.output, "evaluation")
    rows = []
    last_dispatch = None
    for case in dataset:
        for trial in range(args.trials):
            path = output / (case["id"] + "-trial-" + str(trial + 1))
            path.mkdir()
            client = LocalClient(config, path, last_dispatch=last_dispatch)
            # Hidden expected findings never reach the author or reviewers.
            result = run(case["task"], client, path, max_revisions=0, initial_draft=case["draft"])
            last_dispatch = client.last_dispatch
            write_metadata(path, client, config)
            findings = result.get("outstanding_findings", [])
            hits = 0
            for expected in case["expected"]:
                if any(f.get("category") == expected["category"] and
                       len(f.get("evidence", "")) >= 12 and
                       (f["evidence"] in expected["evidence"] or expected["evidence"] in f["evidence"])
                       for f in findings):
                    hits += 1
            complete = result.get("completed", False)
            rows.append({"case": case["id"], "trial": trial + 1, "completed": complete,
                         "expected": len(case["expected"]), "detected": hits if complete else None,
                         "major_findings": sum(f.get("severity") in ("major", "blocker") for f in findings),
                         "status": result["status"], "report": str(path / "report.md")})
            print(case["id"] + ": " + result["status"], flush=True)
    summary = {"mode": "live", "rows": rows,
               "note": "Tiny seeded fixture suite. Detection uses category plus exact evidence overlap; manually audit findings. Clean-case findings may be legitimate, so they are false-positive candidates. No statistical superiority claim."}
    (output / "evaluation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Evaluation: " + str(output / "evaluation.json"))
    return 0 if all(row["completed"] for row in rows) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Harness Lab: local API design review with Elephant and isolated Goldfish.")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Run scripted fixtures, no API or model required")
    demo.add_argument("--output", default="runs")
    discover = sub.add_parser("discover", help="List models from the configured local API")
    discover.add_argument("--config", default="config.local.json")
    live = sub.add_parser("run", help="Draft, review, and revise using your local API")
    live.add_argument("task", nargs="?", default=str(ROOT / "examples/webhook-task.json"))
    live.add_argument("--config", default="config.local.json")
    live.add_argument("--output", default="runs")
    live.add_argument("--max-revisions", type=int, choices=range(0, 4), default=1)
    live.add_argument("--draft", help="Start from a saved draft; author generation is skipped")
    live.add_argument("--review-mode", choices=("legacy", "grounded"), default="legacy",
                      help="Grounded mode uses passage IDs and requires requirement/failure links")
    evaluate = sub.add_parser("evaluate", help="Live seeded review evaluation; never uses scripted model outputs")
    evaluate.add_argument("--config", default="config.local.json")
    evaluate.add_argument("--output", default="runs")
    evaluate.add_argument("--trials", type=int, choices=range(1, 6), default=1)
    evaluate.add_argument("--case", choices=("cross-customer-read", "unbounded-retries", "clean-read-api"),
                          help="Run one seeded case instead of the full suite")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            path = new_run(args.output, "scripted")
            client = ScriptedClient(load_json(ROOT / "examples/demo-responses.json"), path)
            result = run(load_json(ROOT / "examples/webhook-task.json"), client, path)
            write_metadata(path, client, {})
        else:
            config = load_json(args.config)
            if args.command == "discover":
                client = LocalClient(config)
                print(json.dumps({"base_url": client.base_url, "models": client.models()}, indent=2))
                return 0
            if args.command == "evaluate":
                return evaluation(args, config)
            path = new_run(args.output, "live")
            client = LocalClient(config, path)
            config["review_mode"] = args.review_mode
            result = run(load_json(args.task), client, path, max_revisions=args.max_revisions,
                         initial_draft=load_json(args.draft) if args.draft else None, review_mode=args.review_mode)
            write_metadata(path, client, config)
        print_result(result, path)
        return 0 if result["status"] == "ready_for_human_review" else (2 if result["status"] == "needs_attention" else 1)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, ModelError) as exc:
        # Exception details from arbitrary configuration/transport are not echoed; no credentials leak.
        print("Setup/input error (%s). Check task JSON, configuration, credential source, and local API." % type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
