# Grounded review

The first hard benchmark found all six seeded defects, but also exposed two weaknesses: quotation errors cost correction calls, and the EGM template produced major warnings without a demonstrated requirement violation. Grounded mode changes the review interface to address those observed failures. It remains opt-in while evidence is limited.

```powershell
python -m harness_lab run --review-mode grounded
python -m harness_lab run examples/webhook-task.json --draft runs/YOUR-RUN/draft-0.json --max-revisions 0 --review-mode grounded
```

## Citation ownership

Python divides the current draft into paragraphs without crossing list-entry boundaries. Each passage has a section, entry index, exact original text, and an ID. The ID includes a 12-hex-character prefix of a SHA-256 digest of the complete draft and references, followed by its table position. The full digest is saved with the source map. This is an accidental stale-reference check, not a cryptographic security boundary.

Reviewers return a `passage_id`, rather than reconstructing a quotation. Python rejects unknown IDs and resolves a valid ID to the original text and section. It also applies the original exact-evidence validator to that normalized review. All IDs change if any part of the draft or reference set changes, including an unrelated title edit. This deliberately makes every revision require fresh citations.

## Requirement and failure links

Every major or blocker must include:

- A draft passage containing the flawed or incomplete decision.
- One or more `requirement_ids` from the explicit references, problem statement, or goals.
- A `counterexample` with a concrete `scenario` and the resulting `violation`.
- The issue, causal explanation, and recommendation.

Nits can have an empty requirement list and a null counterexample. The validator checks required fields, types, enum values, current IDs, and nonempty arguments. It does not judge the semantic relationship between the scenario and requirement. A model can still produce an unsound argument with valid IDs; human review remains necessary.

Draft goals and the problem statement are candidate requirement sources, not automatically user-approved requirements. Put governing constraints in the task's explicit references; the reviewer still has to interpret them correctly.

The adapter tells reviewers to respect stated scope and accepted tradeoffs, distinguish minimum guarantees from maximum limits, and check whether another passage already prevents the proposed failure. The upstream standard remains a useful checklist; it does not create extra product requirements. This is a substantive adaptation of EGM severity and scope instructions, beyond the legacy formatting-only adapter. Vendored upstream files remain unchanged.

## Isolation, repair, and artifacts

Each reviewer receives only a new system message and the source map derived from the current draft and explicit references. Planning notes, other reviews, and prior conversations are excluded. Reviewer findings and their proposed failure scenarios reach the author only during a revision. The next review starts from a new source map, without previous findings.

An invalid ID or incomplete major finding gets the same single correction attempt as invalid JSON in legacy mode. A second failure marks the run incomplete. The validator never changes severity, removes a finding, fabricates an ID, or silently accepts a partial review.

`grounding-N.json` stores source text and IDs. Each `review-N-PERSONA-grounded.json` preserves accepted model arguments; the ordinary review file stores normalized exact evidence. The report shows both findings and requirement/failure links. Transport traces also retain rejected responses. The author receives the normalized reviews, original arguments, and source map when revising.

## Evaluation boundaries

`scripts/run_grounded_benchmark.py` freezes sources and protocol before live requests. It runs the new mode on the six previously observed hard cases and compares legacy and grounded EGM on one new defective/corrected inventory pair. Both modes use two independent reviews with the same output limits and model group. The fresh pair reverses execution order between counterparts. No labels or stored counterexamples enter model requests.

The original dataset, matcher, and recorded results are preserved. The corrected worker counterpart has a known additional retry-accounting flaw; its alerts cannot automatically be called false positives. Every major finding needs an audit against the actual design. Development results are exploratory before/after evidence. The fresh pair is authored in this project, is only one domain, and is not independent human adjudication. Model-provider routing and actual token usage can differ between calls.

The extra argument fields can increase output tokens. Reliable citations do not guarantee fewer total tokens, better recall, or fewer unsupported warnings. Report those outcomes from live measurements rather than treating the interface change as proof of improvement.

See [the measured comparison and audit](grounded-benchmark.md) for the recorded outcome, including regressions.
