"""Predeclared diagnostic matches, never a substitute for semantic auditing."""
import re


def match_defects(case, findings):
    matches = {}
    for expected in case["expected"]:
        hits = []
        for index, finding in enumerate(findings):
            # Validation already establishes exact quotation. Require both
            # localization and all causal concepts, not just a broad category.
            evidence = finding.get("evidence", "")
            localized = any(anchor.lower() in evidence.lower() or
                            (len(evidence) >= 15 and evidence.lower() in anchor.lower())
                            for anchor in expected["anchors"])
            text = finding.get("issue", "") + " " + finding.get("recommendation", "")
            if localized and all(re.search(pattern, text, re.I) for pattern in expected["concepts"]):
                hits.append(index)
        matches[expected["id"]] = hits
    return matches


def metrics(rows, arm):
    selected = [row for row in rows if row["arm"] == arm]
    if not selected:
        return None
    expected = sum(row["expected"] for row in selected)
    hits = sum(row["detected"] or 0 for row in selected)
    complete = sum(row["completed"] for row in selected)
    controls = [row for row in selected if row["expected"] == 0 and row["completed"]]
    return {
        "case_trials": len(selected), "completed": complete,
        "completion_percent": 100 * complete / len(selected),
        "expected_defects": expected, "detected_defects": hits,
        "delivered_detection_percent": 100 * hits / expected if expected else None,
        "completed_clean_controls": len(controls),
        "controls_with_major_alerts": sum(row["major_findings"] > 0 for row in controls),
        "clean_control_major_alert_percent": 100 * sum(row["major_findings"] > 0 for row in controls) / len(controls) if controls else None,
        "http_attempts": sum(row["attempts"] for row in selected),
        "reported_total_tokens": sum(row["total_tokens"] for row in selected),
        "validation_errors": sum(row["validation_errors"] for row in selected),
    }
