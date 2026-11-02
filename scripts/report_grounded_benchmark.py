"""Export every frozen trial and its arguments; no semantic judgment is automated."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness_lab.contracts import validate_review
from harness_lab.grounded import normalize_review
from harness_lab.runtime import _decode


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def invocation_outcomes(events, case, mode):
    """Count both planned reviews, even when budget failure prevents dispatch."""
    rows = []
    for role in ("comprehension", "design_critic"):
        outcomes = [e for e in events if e.get("role") == role and e["event"] in ("response", "error")]

        def valid(event):
            if not event or event["event"] != "response":
                return False
            try:
                parsed = _decode(event["text"])
                if mode == "grounded":
                    normalize_review(parsed, case["draft"], case["task"]["references"])
                else:
                    validate_review(parsed, case["draft"])
                return True
            except (ValueError, KeyError, TypeError):
                return False

        responses = [e for e in outcomes if e["event"] == "response"]
        first_response_valid = valid(responses[0]) if responses else False
        final_valid = valid(outcomes[-1]) if outcomes else False
        rows.append({"role": role, "dispatched": bool(outcomes),
                     "first_attempt_valid": valid(outcomes[0]) if outcomes else False,
                     "first_response_valid": first_response_valid, "final_valid": final_valid,
                     "validation_repaired": bool(responses) and not first_response_valid and final_valid,
                     "http_errors": sum(e["event"] == "error" for e in outcomes),
                     "routes": sorted({e["routed_via"] for e in responses if e.get("routed_via")})})
    return rows


def export(directory):
    data = read(directory / "comparison.json")
    if len(data["rows"]) != len(data["protocol"]["schedule"]):
        raise ValueError("Experiment incomplete: retain it, but do not publish a final summary")
    cases = {}
    for filename in ("hard-evaluation.json", "grounded-transfer.json"):
        cases.update({case["id"]: case for case in read(directory / "sources/examples" / filename)})
    # Check frozen bytes rather than silently measuring against changed fixtures.
    for name, digest in data["protocol"]["source_sha256"].items():
        if hashlib.sha256((directory / "sources" / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Source snapshot checksum mismatch: " + name)
    for name in ("grounded.py", "contracts.py", "runtime.py"):
        current = hashlib.sha256((ROOT / "harness_lab" / name).read_bytes()).hexdigest()
        if current != data["protocol"]["source_sha256"]["harness_lab/" + name]:
            raise ValueError("Run this exporter using the frozen validators: " + name)
    planned = sorted(tuple(item) for item in data["protocol"]["schedule"])
    observed = sorted((r["case"], r["suite"], r["arm"]) for r in data["rows"])
    if planned != observed:
        raise ValueError("Observed rows do not match the complete frozen schedule")
    for row in data["rows"]:
        path = directory / row.pop("result")
        result = read(path / "result.json")
        events = [json.loads(line) for line in (path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
        metadata = read(path / "metadata.json")
        for name, digest in metadata["source_sha256"].items():
            if digest != data["protocol"]["source_sha256"]["harness_lab/" + name]:
                raise ValueError("Runtime changed during generation: " + name)
        row.update(findings=result["outstanding_findings"], grounded_reviews=result["grounded_reviews"],
                   validation_details=result["validation_errors"], errors=result["errors"],
                   invocations=invocation_outcomes(events, cases[row["case"]], row["arm"]),
                   configuration=metadata["configuration"],
                   model_responses=[{key: event[key] for key in ("role", "text", "resolved_model", "routed_via", "usage") if key in event}
                                    for event in events if event["event"] == "response"])
        if row["arm"] == "grounded":
            row["source_map"] = read(path / "grounding-0.json")
    data["lf_normalized_source_sha256"] = {
        name: hashlib.sha256((directory / "sources" / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in data["protocol"]["source_sha256"]}
    data["semantic_audit"] = "See docs/grounded-benchmark.md; assistant audit, not independent human adjudication. Raw findings and arguments above are preserved."
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    data = export(Path(args.run_directory).resolve())
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(destination)
    print(json.dumps(data["metrics"]))


if __name__ == "__main__":
    main()
