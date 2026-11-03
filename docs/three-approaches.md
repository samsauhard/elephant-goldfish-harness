# Three approaches to design review

The repository exposes three runnable approaches through one CLI. Each consumes the same design and references. This makes execution differences inspectable without maintaining three copies of the project.

## Run all three

Requires Python 3.9+, no pip dependencies, and an existing OpenAI-compatible loopback API. Copy `config.example.json` to `config.local.json`, select a supported model ID, and set `HARNESS_API_KEY` if your server requires a key. See the main README for the existing local-router configuration and optional credential sources.

```powershell
python -m harness_lab review --approach direct
python -m harness_lab review --approach egm
python -m harness_lab review --approach grounded
```

Each command uses `examples/review-task.json` and `examples/review-draft.json`, extracted unchanged from the synthetic defective worker in the original hard benchmark. Only the task and draft are copied; the benchmark's hidden labels and expected counterexamples are not sent to the model. These are demonstration inputs, not a new held-out evaluation.

For another design:

```powershell
python -m harness_lab review --approach direct --task my-task.json --draft my-draft.json --model YOUR_MODEL_ID
python -m harness_lab review --approach egm --task my-task.json --draft my-draft.json --model YOUR_MODEL_ID
python -m harness_lab review --approach grounded --task my-task.json --draft my-draft.json --model YOUR_MODEL_ID
```

Use `--config` to select another local configuration and `--output` to change the output parent. The file shapes match the checked-in examples. The task brief and author planning notes are not sent to reviewers; all three receive only the design and explicit references, plus their review instructions.

## What each approach does

| Property | Direct API | With EGM | EGM + grounded harness |
| --- | --- | --- | --- |
| Reviewer roles | One general reviewer | Comprehension and design critic | Same two EGM roles |
| Author/revision calls in `review` command | None | None | None |
| Generated output | Plain text | JSON findings | JSON evidence arguments, normalized to findings |
| Citation enforcement | None | Exact quote in named design section | Passage ID bound to draft and reference content |
| Requirement and failure-scenario enforcement | None | Not required by validator | Required for major/blocker findings |
| Output corrections | None | One per logical review | One per logical review |
| Transport retries | Disabled | Configurable and budgeted | Configurable and budgeted |
| Generation HTTP limit | Exactly one possible attempt | Configured request budget | Configured request budget |
| Human inspection | Required | Required | Required |

The direct mode overrides `json_mode=false`, `transport_retries=0`, and `max_requests=1`. It uses the common HTTP client for endpoint validation, credentials, timeout/output limits, API-envelope checks, tracing, and redaction of the configured key. It does not check the generated answer's schema, quotations, arguments, or correctness. Provider-side internal retries are outside this application's control.

The EGM mode maps to the original `legacy` adapter. It already uses basic harness infrastructure. The grounded mode adds a stricter evidence contract; this is not a clean ablation of every harness feature against an unwrapped API.

## Artifacts and exit codes

Each command prints its report and trace paths. All paths are under a new, ignored run directory.

- Direct: `response.txt`, `result.json`, `report.md`, `trace.jsonl`, and `metadata.json`. Success is explicitly `response_received_unvalidated`, not an approval. Failure keeps a result/report and does not retry.
- EGM: versioned design, both validated reviews, result/report, trace, and metadata.
- Grounded: the EGM artifacts plus source maps and the original requirement/counterexample arguments.

Exit 0 means a direct response was received, or an EGM review finished without outstanding major findings. Exit 2 means EGM review findings still need attention. Exit 1 means input, setup, or execution failed. No exit code establishes semantic correctness. Traces may contain your input and model output; keep private runs out of Git.

## Which is best on the recorded evidence?

The **saved single-review baseline gave the best token efficiency on the tested designs**. Grounded EGM gave more inspectable evidence and fewer unsupported serious warnings than original EGM. Original EGM's extra reviewer roles did not improve planted-bug detection in this experiment. None is established as the best approach on general tasks.

The following November 2, 2026 results are preserved historical measurements. The first column is the generic reviewer **with basic validation and repair**, not the new raw direct command. The grounded run occurred later than the other two.

| Six existing designs | Saved single-review baseline | Original EGM | Grounded EGM |
| --- | ---: | ---: | ---: |
| Planted bugs detected | 6/6 | 6/6 | 6/6 |
| Unsupported major warnings, assistant audit | Not exhaustively labeled | 10 | 7 |
| All major/blocker findings, including duplicates | 9 | 22 | 18 |
| Minor comments | 5 | 5 | 25 |
| Valid on first response | 4/6 | 10/12 | 8/12 |
| Valid after allowed correction | 6/6 | 12/12 | 12/12 |
| Correction calls | 2 | 2 | 4 |
| HTTP attempts | 8 | 14 | 16 |
| Reported tokens | 19,845 | 53,620 | 83,518 |

Grounded versus original EGM: **30% fewer unsupported major warnings**, **55.8% more tokens**, and **0 percentage-point change in planted detection**. Grounded used 4.21 times the tokens of the saved single-review baseline. That baseline also found an additional worker retry-accounting flaw missed by both EGM versions.

On the two new inventory designs, original versus grounded EGM had 5 versus 1 unsupported major warnings (**80% fewer**), 26,749 versus 38,131 tokens (**42.6% more**), and 2/2 planted bugs found by both. No generic or raw direct baseline was run on that pair.

Two generic reviews were also measured to control logical call count: 6/6 planted detections, 35,329 tokens, and 14 HTTP attempts. Original EGM used 51.8% more tokens with no extra planted detection. Provider routes and actual compute were not held identical.

These are small synthetic experiments with one trial per design and assistant audit labels. They do not establish statistical superiority, overall accuracy, or production reliability. A major alert on a corrected counterpart is not automatically a false positive. Input fixtures, failures, corrections, and unfavorable results remain available.

The new direct entry point was added on November 3, 2026 and checked with fake HTTP responses. It has **not** been assigned the old baseline's measured performance, and publication does not imply a new live three-arm benchmark.

## Evidence and interactive view

- [Original generic/EGM benchmark](hard-benchmark.md) and [semantic audit](hard-benchmark-audit.md).
- [Grounded benchmark](grounded-benchmark.md) and [all audit labels](../benchmarks/results/2026-11-02-grounded-audit.json).
- [Original machine-readable results](../benchmarks/results/2026-11-02-hard.json).
- [Grounded machine-readable results](../benchmarks/results/2026-11-02-grounded.json).
- [Static comparison website](../site/README.md): three approach explanations, full metric tables, graphs, and a step-through inventory example.

The site is a snapshot of those recorded experiments, including their historical 70-test count. The current source has **76 passing automated tests**, including the new three-approach CLI/transport checks. Test success is software verification, not model-quality evidence.
