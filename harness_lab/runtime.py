"""An inspectable author/reviewer loop with bounded, isolated model calls."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from .client import BudgetExceeded
from .contracts import REVIEW_PERSONAS, validate_draft, validate_review, validate_task
from .prompts import author_messages, reviewer_messages, revision_messages


class _InvalidModelOutput(ValueError):
    """Both the initial response and its single correction failed validation."""


def _write_json(path: Path, data: Any) -> None:
    _write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _write_text(path: Path, text: str) -> None:
    # Runs use their own directory. Direct writes also work in restricted Windows
    # temporary directories where replacement/rename permission is unavailable.
    # This v1 preserves completed steps, but does not promise crash-safe resume.
    path.write_text(text, encoding="utf-8")


def _unique_keys(pairs: list) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Model JSON contains duplicate object keys")
        value[key] = item
    return value


def _invalid_constant(_value: str) -> None:
    raise ValueError("Model JSON contains a nonstandard numeric constant")


def _decode(text: Any) -> dict:
    if not isinstance(text, str):
        raise ValueError("Model response text must be a string containing JSON")
    try:
        value = json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_invalid_constant)
    except json.JSONDecodeError:
        raise ValueError("Model response must contain one valid JSON object without Markdown") from None
    if not isinstance(value, dict):
        raise ValueError("Model response must be a JSON object")
    return value


def _structured_call(
    client: Any,
    messages: list,
    role: str,
    validator: Callable[[dict], None],
    summary: dict,
    stage: str,
) -> dict:
    # Copy before each call so a client retaining requests cannot observe later
    # mutation. Corrections belong only to this logical call's conversation.
    original_messages = copy.deepcopy(messages)
    request = original_messages
    for attempt in range(2):
        response = client.complete(copy.deepcopy(request), role=role)
        raw_text = response.get("text") if isinstance(response, dict) else None
        try:
            parsed = _decode(raw_text)
            validator(parsed)
            return parsed
        except ValueError as exc:
            # These messages originate in our validators; never stringify an
            # arbitrary transport exception or response into the report.
            message = str(exc)
            summary["validation_errors"].append({
                "stage": stage, "attempt": attempt + 1, "message": message
            })
            if attempt:
                raise _InvalidModelOutput("Model output failed validation after one correction") from None
            summary["correction_attempts"] += 1
            request = copy.deepcopy(original_messages)
            if isinstance(raw_text, str):
                request.append({"role": "assistant", "content": raw_text})
            request.append({
                "role": "user",
                "content": (
                    "Correct the previous response. Return only one JSON object following "
                    "the original schema and instructions. Validation failed: " + message
                    + ". Do not add explanations or Markdown fences."
                ),
            })
    raise AssertionError("Unreachable correction loop")


def _findings(reviews: dict) -> list:
    return [
        dict(finding, persona=persona)
        for persona, review in reviews.items()
        for finding in review["findings"]
    ]


def _client_metadata(client: Any, summary: dict) -> None:
    mode = getattr(client, "mode", "unknown")
    summary["mode"] = mode if mode in ("live", "scripted") else "unknown"
    model = getattr(client, "model", None)
    summary["model"] = model if isinstance(model, str) else None
    attempts = getattr(client, "attempts", None)
    summary["attempts"] = attempts if isinstance(attempts, int) else None


def _design_markdown(draft: dict) -> str:
    """Render the latest validated design without asking a model to rewrite it."""
    lines = ["# " + draft["title"], ""]
    for field, heading in (
        ("problem", "Problem"), ("goals", "Goals"), ("design", "Design"),
        ("alternatives", "Alternatives"), ("risks", "Risks"),
        ("acceptance_tests", "Acceptance tests"), ("open_questions", "Open questions"),
    ):
        lines += ["## " + heading, ""]
        content = draft[field]
        if isinstance(content, list):
            lines += ["- " + item.replace("\n", "\n  ") for item in content] if content else ["None recorded."]
        else:
            lines.append(content)
        lines.append("")
    return "\n".join(lines)


def _report(summary: dict, task: dict) -> str:
    title = task.get("title", "Untitled task") if isinstance(task, dict) else "Invalid task"
    lines = [
        "# Harness Lab run", "", str(title), "",
        "- Status: **" + summary["status"] + "**",
        "- Mode: " + summary["mode"],
        "- Completed review round: " + ("yes" if summary["completed"] else "no"),
        "- Revisions used: " + str(summary["revisions_used"]),
        "- JSON correction attempts: " + str(summary["correction_attempts"]),
        "", 
    ]
    if summary["mode"] == "scripted":
        lines += [
            "This run used scripted offline fixtures. It verifies workflow plumbing and "
            "provides no evidence of model quality.", ""
        ]
    lines += [
        "Ready for human review means both reviewers returned valid JSON and no blocker "
        "or major findings remain. It is not proof that the design is correct or safe. "
        "Exact evidence checks establish text grounding, not semantic correctness.", ""
    ]
    if summary["failure_reason"]:
        lines += ["Run note: `" + summary["failure_reason"] + "`.", ""]
    if summary["errors"]:
        lines += ["## Errors", ""]
        for error in summary["errors"]:
            lines += ["- " + error["stage"] + ": " + error["message"]]
        lines += [""]
    lines += ["## Latest review findings", ""]
    if not summary["completed"]:
        lines += ["This review round is incomplete. Absence of findings is not a clean result.", ""]
    if not summary["outstanding_findings"]:
        lines += ["No findings recorded in the latest review round.", ""]
    for finding in summary["outstanding_findings"]:
        lines += [
            "### " + finding["severity"].upper() + " / " + finding["persona"] + " / " + finding["category"],
            "", finding["issue"], "",
            "Section: `" + finding["section"] + "`", "",
            "> " + finding["evidence"].replace("\n", "\n> "), "",
            "Recommendation: " + finding["recommendation"], "",
        ]
    lines += ["## Artifacts", ""]
    if summary["final_design"]:
        lines += ["- [Latest design](design.md)"]
    for filename in summary["drafts"] + summary["review_artifacts"]:
        lines += ["- [" + filename + "](" + filename + ")"]
    lines += ["- [result.json](result.json)", ""]
    return "\n".join(lines)


def run(
    task: dict,
    client: Any,
    run_dir: Path,
    max_revisions: int = 1,
    initial_draft: dict | None = None,
) -> dict:
    """Draft, review independently, and optionally revise within fixed limits.

    Client.complete owns HTTP retries, attempt budgeting, timing, and traces.
    Technical failure returns status='failed' and preserves completed artifacts;
    remaining major findings return status='needs_attention'. Neither is ready.
    A seed draft starts a new run and is always reviewed before it can be ready.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "failed",
        "completed": False,
        "failure_reason": None,
        "final_round": None,
        "revisions_used": 0,
        "max_revisions": max_revisions,
        "correction_attempts": 0,
        "drafts": [],
        "final_draft": None,
        "final_design": None,
        "reviews": {},
        "review_artifacts": [],
        "outstanding_findings": [],
        "remaining_major_findings": 0,
        "validation_errors": [],
        "errors": [],
    }
    stage = "validate_input"
    try:
        validate_task(task)
        if isinstance(max_revisions, bool) or not isinstance(max_revisions, int) or max_revisions < 0:
            raise ValueError("max_revisions must be a nonnegative integer")
        if initial_draft is None:
            stage = "author"
            draft = _structured_call(client, author_messages(copy.deepcopy(task)), "author", validate_draft, summary, stage)
        else:
            stage = "validate_seed"
            validate_draft(initial_draft)
            draft = copy.deepcopy(initial_draft)

        for round_number in range(max_revisions + 1):
            summary["final_round"] = round_number
            summary["revisions_used"] = round_number
            summary["completed"] = False
            summary["reviews"] = {}
            summary["outstanding_findings"] = []
            summary["remaining_major_findings"] = 0
            filename = "draft-" + str(round_number) + ".json"
            stage = "save_" + filename
            _write_json(run_dir / filename, draft)
            summary["drafts"].append(filename)
            summary["final_draft"] = filename
            stage = "save_design.md"
            _write_text(run_dir / "design.md", _design_markdown(draft))
            summary["final_design"] = "design.md"

            for persona in REVIEW_PERSONAS:
                stage = "review_" + str(round_number) + "_" + persona
                # These are the only data passed to each reviewer. Never pass
                # the task, author-only notes, another review, or history.
                messages = reviewer_messages(copy.deepcopy(draft), copy.deepcopy(task["references"]), persona)
                review = _structured_call(
                    client, messages, persona,
                    lambda candidate: validate_review(candidate, draft), summary, stage,
                )
                filename = "review-" + str(round_number) + "-" + persona + ".json"
                stage = "save_" + filename
                _write_json(run_dir / filename, review)
                summary["review_artifacts"].append(filename)
                summary["reviews"][persona] = review
                summary["outstanding_findings"] = _findings(summary["reviews"])
                summary["remaining_major_findings"] = sum(
                    finding["severity"] in ("blocker", "major") for finding in summary["outstanding_findings"]
                )

            summary["completed"] = True
            if not summary["remaining_major_findings"]:
                summary["status"] = "ready_for_human_review"
                break
            if round_number == max_revisions:
                summary["status"] = "needs_attention"
                summary["failure_reason"] = "revision_limit_reached"
                break
            stage = "revision_" + str(round_number + 1)
            draft = _structured_call(
                client,
                revision_messages(copy.deepcopy(task), copy.deepcopy(draft), copy.deepcopy(summary["reviews"])),
                "revision", validate_draft, summary, stage,
            )
    except _InvalidModelOutput:
        summary["status"] = "failed"
        summary["failure_reason"] = "invalid_model_output"
        summary["errors"].append({"stage": stage, "type": "validation", "message": "Model output failed validation after one correction."})
    except ValueError as exc:
        summary["status"] = "failed"
        summary["failure_reason"] = "invalid_input"
        # Only expose our input-validation errors. Other ValueErrors may come
        # from a client, whose message could contain credentials or raw bodies.
        message = str(exc) if stage in ("validate_input", "validate_seed") else "A model or prompt operation rejected its input."
        summary["errors"].append({"stage": stage, "type": "validation", "message": message})
    except BudgetExceeded:
        summary["status"] = "failed"
        summary["failure_reason"] = "request_budget_exhausted"
        summary["errors"].append({
            "stage": stage, "type": "budget",
            "message": "The request budget was exhausted. Completed artifacts have been preserved.",
        })
    except Exception as exc:
        summary["status"] = "failed"
        summary["failure_reason"] = "execution_failed"
        summary["errors"].append({
            "stage": stage, "type": type(exc).__name__,
            "message": "The operation failed. Inspect the local transport trace for sanitized details.",
        })
    # A previous round may have finished before a revision failed. The workflow
    # is still incomplete; its previous draft and review artifacts remain useful.
    if summary["status"] == "failed":
        summary["completed"] = False
    _client_metadata(client, summary)
    _write_json(run_dir / "result.json", summary)
    _write_text(run_dir / "report.md", _report(summary, task))
    return summary
