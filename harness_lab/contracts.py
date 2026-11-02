"""Small, deterministic contracts for task, draft, and review artifacts.

Validation establishes shape and that evidence was actually present in a draft.
It cannot establish whether a model's reasoning or a design is correct.
"""

from __future__ import annotations

from typing import Any


DRAFT_TEXT_FIELDS = ("title", "problem", "design")
DRAFT_LIST_FIELDS = (
    "goals", "alternatives", "risks", "acceptance_tests", "open_questions"
)
DRAFT_FIELDS = DRAFT_TEXT_FIELDS + DRAFT_LIST_FIELDS
REVIEW_PERSONAS = ("comprehension", "design_critic")
SEVERITIES = ("blocker", "major", "nit")
CATEGORIES = ("security", "reliability", "clarity", "scope", "testing")
MAX_FINDINGS = 12


def _object(value: Any, name: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(name + " must be a JSON object")


def _keys(value: dict, required: tuple, optional: tuple, name: str) -> None:
    if not set(required).issubset(value):
        raise ValueError(name + " is missing required fields")
    if set(value).difference(required + optional):
        raise ValueError(name + " contains unsupported fields")


def _text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " must be a nonempty string")


def _text_list(value: Any, name: str, allow_empty: bool = False) -> None:
    if not isinstance(value, list):
        raise ValueError(name + " must be a list of strings")
    if not value and not allow_empty:
        raise ValueError(name + " must contain at least one string")
    for item in value:
        _text(item, name + " entries")


def validate_task(task: Any) -> None:
    """Validate an inline task; reference entries are text, never file paths."""
    _object(task, "task")
    _keys(task, ("title", "brief", "references"), ("planning_notes",), "task")
    _text(task["title"], "task.title")
    _text(task["brief"], "task.brief")
    _text_list(task["references"], "task.references", allow_empty=True)
    if "planning_notes" in task and not isinstance(task["planning_notes"], str):
        raise ValueError("task.planning_notes must be a string")


def validate_draft(draft: Any) -> None:
    """Require a structured design; only open_questions may be an empty list."""
    _object(draft, "draft")
    _keys(draft, DRAFT_FIELDS, (), "draft")
    for name in DRAFT_TEXT_FIELDS:
        _text(draft[name], "draft." + name)
    for name in DRAFT_LIST_FIELDS:
        _text_list(draft[name], "draft." + name, allow_empty=name == "open_questions")


def validate_review(review: Any, draft: Any) -> None:
    """Validate findings and exact evidence within the named draft section.

For a list section, evidence must occur in one actual entry, not in a JSON
serialization or across the boundary between adjacent entries.
"""
    validate_draft(draft)
    _object(review, "review")
    _keys(review, ("summary", "findings"), (), "review")
    _text(review["summary"], "review.summary")
    findings = review["findings"]
    if not isinstance(findings, list):
        raise ValueError("review.findings must be a list")
    if len(findings) > MAX_FINDINGS:
        raise ValueError("review.findings exceeds the 12-finding limit")
    required = ("severity", "category", "section", "evidence", "issue", "recommendation")
    invalid_evidence = []
    for index, finding in enumerate(findings):
        _object(finding, "finding")
        _keys(finding, required, (), "finding")
        for name in required:
            _text(finding[name], "finding." + name)
        if finding["severity"] not in SEVERITIES:
            raise ValueError("finding.severity must be blocker, major, or nit")
        if finding["category"] not in CATEGORIES:
            raise ValueError("finding.category is unsupported")
        if finding["section"] not in DRAFT_FIELDS:
            raise ValueError("finding.section must name an existing draft field")
        section = draft[finding["section"]]
        passages = section if isinstance(section, list) else [section]
        if not any(finding["evidence"] in passage for passage in passages):
            invalid_evidence.append("findings[%s] in %s" % (index, finding["section"]))
    if invalid_evidence:
        raise ValueError("finding.evidence must be an exact substring of a section entry; "
                         "incorrect quotes or section names: " + ", ".join(invalid_evidence))
