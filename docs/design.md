# Harness Lab: local API design review

Status: initial implementation specification. Scope: an API-driven adaptation of EGM with two isolated reviewers.

Implementation update: an opt-in [grounded review mode](grounded-review.md) now adds document-bound passage IDs and requirement/counterexample arguments. The legacy interface described below remains available and is the default. The grounded adapter also calibrates severity and scope against the supplied requirements; vendored EGM files remain unchanged.

## Problem and scope

Build a small, understandable Python 3.9+ harness that turns an API feature brief into a design, reviews it with isolated model calls, and proposes revisions. It must run against the user's existing local LLM API. An offline scripted demo verifies plumbing without claiming to measure model intelligence. No external framework, model training, shell tools, model-written code execution, or deployment is needed.

## Workflow

1. Load an explicit JSON task: title, brief, reference materials, and optional author-only planning notes.
2. Elephant drafts a structured design with project context.
3. Two independent Goldfish calls inspect only that draft and the explicit reference materials: comprehension and design critic. Each starts with fresh system/user messages. Prior conversation, author planning notes, and the other reviewer's findings are excluded from its request.
4. Deterministic validation checks JSON types, required nonempty sections, and exact evidence quotes in review findings. These checks establish structure and grounding, not semantic correctness.
5. Elephant may revise using findings, within a fixed number of rounds and HTTP attempts. The revised draft is reviewed again. Final status is ready_for_human_review if structural checks pass and no blocker/major findings remain, otherwise needs_attention. No model approves or deploys a design.
6. Save every request/response, errors, timing, token usage if reported, each draft/review, and a Markdown report to a unique run directory. API credentials never go in artifacts. User-provided task content is recorded locally; users should avoid sensitive inputs for shared reports.

## Interfaces

Use the Python standard library and a CLI: `python -m harness_lab discover`, `demo`, `run TASK`, and `evaluate`. Model adapter uses the discovered OpenAI-compatible `/v1/chat/completions` endpoint. The local adapter connects only to a loopback URL and refuses redirects. The discovered FreeLLMAPI router at port 3002 uses authentication and can route requests to hosted models; loopback transport does not imply local inference. Read its existing credential through a read-only SQLite connection or an explicit environment/file source, without copying it into the repository. Configuration records endpoint/model and execution limits. Mock HTTP servers provide transport tests.

Draft JSON fields: title (string), problem (string), goals (list of strings), design (string), alternatives (list of strings), risks (list of strings), acceptance_tests (list of strings), open_questions (list of strings, may be empty).

Review JSON fields: summary (string), findings (list). Each finding: severity (blocker/major/nit), category (security/reliability/clarity/scope/testing), section (draft field), evidence (exact nonempty substring of that field), issue (string), recommendation (string). At most 12 findings. Reviewers must not invent missing evidence; for omissions, quote the existing passage whose incompleteness creates the issue.

## Boundaries and failure behavior

Each transport attempt consumes a request budget, including retry attempts. Timeouts and transient server failures get bounded retries; malformed JSON gets one explicit correction attempt within the same budget. Limits also cap task bytes and output tokens. Exhaustion preserves partial artifacts with a failure status and nonzero exit code. HTTP timeout is not a cancellation guarantee for server-side generation. There is no automatic resume in version one; saved drafts can seed a new run. No arbitrary file access is granted to the model. Referenced material is embedded by the user in the input JSON, not fetched from model-generated paths or URLs.

## Upstream EGM integration

Vendor exact comprehension and design-critic personas and the feature specification standard at a pinned upstream commit, with Apache-2.0 license and source metadata. Load them at runtime as reviewer instructions. A local adapter explains that the target document/reference text is inline, no tools are available, and output must follow the structured JSON contract. This intentionally changes output formatting and reduces EGM's broader review sequence to two reviewers. It does not install the complete EGM plugin or claim official support.

## Evaluation

Unit/integration tests check context isolation, request budgets, evidence validation, malformed model outputs, HTTP failures, artifact persistence, and no false success when reviews are incomplete. A separate seeded design evaluation checks whether actual model reviews detect known flaw categories and records false positives on a clean fixture. Expected answers stay outside model requests. Offline fixture results are explicitly marked scripted and are not quality evidence. Compare live results across model/prompt revisions using the saved settings and traces; a tiny fixture suite cannot establish statistical superiority.

## Alternatives and tradeoffs

- Large orchestration framework: omitted so the control loop, state, isolation, and failure semantics remain inspectable.
- Install the full EGM plugin: supports interactive software design in a coding environment; this runtime instead exposes a standalone CLI with structured review artifacts and explicit request budgets.
- Shared conversation for author and reviewers: simpler but violates fresh reviewer context.
- Parallel local reviewers: potentially faster on capable servers, but sequential calls avoid overloading one local model while retaining independent contexts.
- Unrestricted coding agent: broader tool-use exercise, but would add sandbox requirements unrelated to this first project's design-review objective.

## Acceptance

Offline demo and automated tests pass on local Python. Discover the existing API, verify one real generation, then run a complete live design/review cycle if the endpoint supports it. Report measured outcomes and limitations without substituting scripted outputs for live model evidence.
