# Harness Lab

A small Python harness that drafts an API design, reviews it with independent Elephant-Goldfish model calls, and proposes revisions. It uses basic HTTP requests and the Python standard library, so the orchestration is easy to inspect.

The runtime enforces context boundaries, structured outputs, request budgets, and independent reviews, with evaluation fixtures and trace logs for diagnosing failures. It produces design artifacts for human review.

## What Elephant-Goldfish means

[Google's Elephant-Goldfish Model (EGM)](https://github.com/google/elephant-goldfish-model) is a software design/review workflow and collection of agent skills, not a model checkpoint or inference API.

- **Elephant:** receives the brief, references, and author planning notes; drafts and revises the design.
- **Comprehension Goldfish:** reads the draft and explicit references in a fresh request, looking for unclear explanations and unstated assumptions.
- **Design Critic Goldfish:** independently checks the same material for design problems and failure modes.
- **Human:** reviews the proposal and makes the actual design decisions.

Harness Lab loads the real upstream comprehension and design-critic persona files and feature-spec standard from `vendor/elephant-goldfish/`. They are pinned to commit `36343a16f0e0d830a7ed78b0da97695379ab3243`, preserved unchanged, and accompanied by the Apache-2.0 license. Our prompt adapter supplies inline documents and requires JSON findings. This is a two-reviewer adaptation, not the full EGM plugin or its complete review sequence. The same LLM can play all roles; isolation comes from separate request contexts, not from having different model brands.

## Run it now

Requires Python 3.9 or later. No pip installation or third-party Python packages are needed. Run commands from this repository directory.

```powershell
python -m harness_lab demo
python -m unittest discover -s tests -v
```

`demo` uses canned responses, spends no API calls, and is explicitly labeled **scripted** in its output. It verifies the workflow and demonstrates artifacts; its success is not evidence of model quality.

For the local API already configured on this PC:

```powershell
python -m harness_lab discover
python -m harness_lab run
```

The first command lists models. The second uses `examples/webhook-task.json`, runs two isolated reviewers, and permits one revision followed by another review. A successful process exit means **ready for human review**, not approved or proven correct. Exit 2 means review findings remain; exit 1 means execution or input failed. Every run gets a separate directory under `runs/`.

## Local API setup

The discovered endpoint is `http://127.0.0.1:3002/v1`, the existing FreeLLMAPI router reached over an SSH tunnel. `auto:business-free` worked in a live JSON response test. The router may select hosted providers: a loopback API address does not mean the model runs on this PC or that prompt data stays on it. Use the included synthetic example for your first runs.

`config.local.json` is machine-specific and gitignored. On this PC it reads the existing unified API key from the FreeLLM database in read-only mode. The credential is not copied into this project or printed. The tunnel and router must already be running; Harness Lab does not change or launch them.

For another machine, copy `config.example.json` to `config.local.json`, choose your loopback `/v1` endpoint and a real model ID, and provide the key in `HARNESS_API_KEY` if the server requires one. The adapter supports OpenAI-compatible chat completion APIs; it does not implement the OpenAI hosted service, Gemini SDK, or Ollama native protocol. Ollama can be used through its OpenAI-compatible `/v1` endpoint if supported by the installed version.

Configuration options:

| Setting | Meaning |
| --- | --- |
| `base_url`, `model` | Local compatible API and routing/model ID |
| `api_key_env` | Environment variable containing the key; defaults to `HARNESS_API_KEY` |
| `api_key_sqlite_path` | Optional existing FreeLLM database; reads only `settings.unified_api_key` |
| `api_key_file`, `api_key_field` | Optional explicit plain-text or nested-JSON credential file; no automatic filesystem search |
| `json_mode` | Send `response_format: {type: json_object}`; turn off only if the server lacks this option |
| `max_requests` | Hard limit on generation HTTP attempts, including retries and JSON corrections |
| `max_output_tokens` | Requested per-response generation cap, enforced by the server |
| `timeout_seconds` | Per-request network timeout; it does not cancel server-side generation |
| `transport_retries` | Retry count for transient failures; non-transient failures stop immediately |
| `min_interval_seconds` | Minimum time between generation attempts; configured to 60 seconds for the existing free router |

An environment credential takes precedence over the configured database or file. Request and output limits bound work; this project does not estimate API charges. An automatic free-model router is convenient for development but can select different models across calls. Traces record the returned model and routing header when provided; select a fixed model ID for controlled comparisons.

Retries honor `Retry-After` cooldowns up to 60 seconds. Longer requested cooldowns end the run with an error so it can be retried later. Pacing reduces minute-limit failures but does not guarantee provider quota availability. A full live run may take several minutes.

## Use your own task

Copy `examples/webhook-task.json` and edit:

```json
{
  "title": "My API feature",
  "brief": "Describe the problem, scope, and desired behavior.",
  "references": ["Explicit requirements and relevant existing-system details."],
  "planning_notes": "Optional context for the author only."
}
```

```powershell
python -m harness_lab run examples/my-task.json --max-revisions 1
```

References are inline text. The harness does not fetch model-provided URLs or read model-provided file paths. Reviewer requests contain only the current draft and explicit references, plus their persona/rubric. They exclude author planning notes, prior messages, and other reviewers' findings. Facts the author writes into the draft are naturally visible to reviewers; this is conversation isolation, not a guarantee that the author will keep facts secret.

To review a saved or manually edited draft in a new run:

```powershell
python -m harness_lab run examples/webhook-task.json --draft runs/YOUR-RUN/draft-0.json --max-revisions 0
```

This starts a fresh review; automatic interruption recovery is not implemented.

## Inspect what happened

Each run preserves:

- `draft-N.json`: versioned structured designs.
- `design.md`: readable latest valid design.
- `review-N-comprehension.json` and `review-N-design_critic.json`: grounded reviewer findings.
- `trace.jsonl`: actual requests, responses, errors, timing, and reported usage.
- `result.json` and `report.md`: completion state, outstanding issues, corrections, and artifact links.
- `metadata.json`: safe configuration, requested/resolved model IDs, usage when available, and upstream EGM revision.

Traces include task content and model output. The configured credential is redacted, but there is no general-purpose detector for unrelated sensitive material you place in a task. Keep local runs out of source control and redact sensitive content before sharing examples.

Malformed JSON, invented evidence quotes, incomplete reviews, connection failures, and exhausted budgets cannot produce a clean result. Shape validation and exact quotations verify format and text grounding only; they do not prove that a finding is sound or that the design is secure. Inspect the artifacts and use human judgment.

## Evaluate reviewer behavior

```powershell
python -m harness_lab evaluate
python -m harness_lab evaluate --case cross-customer-read
python -m harness_lab evaluate --trials 3
```

This runs actual API reviews on three checked-in designs: a cross-customer data leak, unbounded retries, and a cleaner read-only control. Expected labels are withheld from model requests. Each trial makes two reviewer calls plus any bounded corrections/retries, with a separate request budget per case/trial. `--trials 3` therefore reviews nine case instances, not three API calls.

The resulting `evaluation.json` records completion, seeded flaw detection, and potential false positives. Detection uses the flaw category and an exact evidence overlap. It is a narrow diagnostic, can miss valid paraphrased localizations, and needs manual review. A major finding on the clean control is a false-positive candidate, not automatically an error. Technical failures are not scored as clean reviews. This tiny suite does not establish statistical superiority or general design-review quality.

## Architecture

| File | Responsibility |
| --- | --- |
| `harness_lab/runtime.py` | Control loop, state transitions, revision limits, failure recovery artifacts |
| `harness_lab/prompts.py` | Context engineering, independent reviewers, adapting upstream prompts |
| `harness_lab/contracts.py` | Typed boundaries and deterministic evidence validation |
| `harness_lab/client.py` | Basic HTTP integration, request accounting, retries, tracing |
| `harness_lab/__main__.py` | Reproducible runs, configuration, seeded evaluation |
| `tests/` | Isolation, failure injection, budget enforcement, malformed-output behavior |

Further evaluation requires a held-out task set comparing author-only designs with reviewed designs, using a fixed model and independent human scoring. Potential extensions include persistent checkpoints and a trace viewer; changes should address observed failures and include reproducible measurements.

See `docs/design.md` for architecture and tradeoffs, and `docs/verification.md` for the recorded checks from initial setup.

## Attribution

Upstream EGM source: <https://github.com/google/elephant-goldfish-model>. Vendored materials are Apache-2.0; see `vendor/elephant-goldfish/LICENSE` and `UPSTREAM.json`. Harness Lab is an independent project and is not an officially supported Google product.

Project source license: Apache-2.0. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
